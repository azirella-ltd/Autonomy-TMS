# Advanced Analytics Components

Phase 6 Sprint 2: Advanced Analytics

## Overview

This directory contains React components for visualizing advanced statistical analysis of supply chain simulation results.

## Components

### 1. SensitivityAnalysis

Tornado diagrams and Sobol indices visualization for parameter sensitivity analysis.

**Features:**
- One-At-a-Time (OAT) sensitivity analysis with tornado diagrams
- Sobol sensitivity indices with bootstrap confidence intervals
- Interactive parameter configuration
- Parameter importance ranking
- Tabbed interface (Visualization, Data Table, Interpretation)

**Usage:**
```jsx
import { SensitivityAnalysis } from './components/advanced-analytics';

<SensitivityAnalysis
  gameId={gameId}
  simulationData={simulationResults}
/>
```

**Props:**
- `gameId` (number): Game ID for analysis
- `simulationData` (array): Pre-computed simulation results with parameter configurations

### 2. CorrelationHeatmap

Interactive correlation matrix heatmap with multiple correlation methods.

**Features:**
- Pearson, Spearman, and Kendall correlation methods
- Color-coded heatmap by correlation strength
- Strong correlation detection and highlighting
- Statistical significance testing (p-values)
- Interactive tooltips with detailed information
- Full correlation matrix table view

**Usage:**
```jsx
import { CorrelationHeatmap } from './components/advanced-analytics';

<CorrelationHeatmap
  metricsData={{
    total_cost: [...],
    inventory: [...],
    service_level: [...],
    backlog: [...]
  }}
/>
```

**Props:**
- `metricsData` (object): Dictionary of metric names to data arrays

### 3. TimeSeriesAnalyzer

Time series analysis with ACF, PACF, decomposition, and forecast accuracy metrics.

**Features:**
- Autocorrelation Function (ACF) plots
- Partial Autocorrelation Function (PACF) plots
- Time series decomposition (trend, seasonal, residual)
- Forecast accuracy metrics (MAPE, RMSE, MAE, R²)
- Multiple model support (additive, multiplicative)
- Significant lag detection
- Interactive lag selection

**Usage:**
```jsx
import { TimeSeriesAnalyzer } from './components/advanced-analytics';

// For ACF/PACF and Decomposition
<TimeSeriesAnalyzer
  timeSeriesData={demandHistory}
/>

// For Forecast Accuracy
<TimeSeriesAnalyzer
  actualData={actualDemand}
  predictedData={forecastedDemand}
/>
```

**Props:**
- `timeSeriesData` (array): Time series data for ACF/PACF and decomposition
- `actualData` (array): Actual values for forecast accuracy
- `predictedData` (array): Predicted values for forecast accuracy

## API Integration

All components integrate with the advanced analytics API endpoints at `/api/v1/advanced-analytics/`:

- `POST /sensitivity` - OAT sensitivity analysis
- `POST /sensitivity/sobol` - Sobol indices
- `POST /correlation` - Correlation matrix
- `POST /time-series/acf` - ACF/PACF analysis
- `POST /time-series/decompose` - Time series decomposition
- `POST /forecast-accuracy` - Forecast accuracy metrics

## Dependencies

- **@mui/material**: Material-UI components
- **recharts**: Charting library for visualizations
- **axios**: HTTP client (via `services/api.js`)

## Mock Data

Each component includes mock data generation for testing purposes when real data is not provided:
- `generateMockData()` - Generate test simulation data
- `generateMockTimeSeries()` - Generate autocorrelated time series
- `generateMockForecasts()` - Generate forecast test data

## Color Schemes

### Correlation Heatmap
- **Strong Positive (≥0.7)**: Blue shades (#1976d2, #1565c0)
- **Moderate Positive (0.5-0.7)**: Light blue (#42a5f5)
- **Weak (0.3-0.5)**: Very light blue (#90caf9)
- **Very Weak (<0.3)**: Gray (#e0e0e0)
- **Moderate Negative (-0.5 to -0.7)**: Light red (#ef5350)
- **Strong Negative (≤-0.7)**: Red shades (#d32f2f, #c62828)

### Time Series
- **Original/Actual**: Black (#000)
- **Trend**: Blue (#1976d2)
- **Seasonal**: Green (#4caf50)
- **Residual**: Red (#f44336)
- **ACF Bars**: Blue (#8884d8)
- **PACF Bars**: Green (#82ca9d)
- **Significant Values**: Red (#f44336)

## Usage Examples

### Example 1: Sensitivity Analysis Dashboard

```jsx
import React from 'react';
import { Grid } from '@mui/material';
import { SensitivityAnalysis, CorrelationHeatmap } from './components/advanced-analytics';

const AnalyticsDashboard = ({ gameId, simulationResults, metricsData }) => {
  return (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <SensitivityAnalysis
          gameId={gameId}
          simulationData={simulationResults}
        />
      </Grid>
      <Grid item xs={12}>
        <CorrelationHeatmap metricsData={metricsData} />
      </Grid>
    </Grid>
  );
};
```

### Example 2: Time Series Analysis

```jsx
import React, { useState, useEffect } from 'react';
import { TimeSeriesAnalyzer } from './components/advanced-analytics';
import api from './services/api';

const TimeSeriesPage = ({ gameId }) => {
  const [demandHistory, setDemandHistory] = useState([]);

  useEffect(() => {
    // Fetch game history
    api.get(`/games/${gameId}/history`)
      .then(response => {
        const demands = response.data.rounds.map(r => r.demand);
        setDemandHistory(demands);
      });
  }, [gameId]);

  return (
    <TimeSeriesAnalyzer timeSeriesData={demandHistory} />
  );
};
```

### Example 3: Monte Carlo Analysis

```jsx
import React from 'react';
import { Box, Grid } from '@mui/material';
import {
  SensitivityAnalysis,
  CorrelationHeatmap,
  TimeSeriesAnalyzer
} from './components/advanced-analytics';

const MonteCarloAnalysis = ({ monteCarloResults }) => {
  // Extract metrics from Monte Carlo runs
  const metricsData = {
    total_cost: monteCarloResults.map(r => r.total_cost),
    holding_cost: monteCarloResults.map(r => r.holding_cost),
    backlog_cost: monteCarloResults.map(r => r.backlog_cost),
    service_level: monteCarloResults.map(r => r.service_level),
  };

  // Extract time series from first run
  const timeSeriesData = monteCarloResults[0].inventory_history;

  return (
    <Box>
      <Grid container spacing={3}>
        <Grid item xs={12} lg={6}>
          <CorrelationHeatmap metricsData={metricsData} />
        </Grid>
        <Grid item xs={12} lg={6}>
          <TimeSeriesAnalyzer timeSeriesData={timeSeriesData} />
        </Grid>
      </Grid>
    </Box>
  );
};
```

## Testing

Each component includes:
- Mock data generation for standalone testing
- Error handling and display
- Loading states
- Empty states with instructions

To test components in isolation:
1. Import component
2. Render without props (uses mock data)
3. Verify visualizations and interactions
4. Test with real data

## Performance Considerations

- **Data Size**: Components handle up to 1000 data points efficiently
- **Rerendering**: Uses React state management to minimize rerenders
- **Responsiveness**: All charts use `ResponsiveContainer` for adaptive sizing
- **Mock Data**: Generated client-side only when real data is unavailable

## Future Enhancements

1. **Export Functionality**: Add buttons to export charts as PNG/SVG
2. **Data Filtering**: Add date range selectors for time series
3. **Comparison Mode**: Compare multiple scenarios side-by-side
4. **Real-time Updates**: WebSocket integration for live analysis
5. **Advanced Tooltips**: Show formulas and calculation details
6. **Customization**: User-configurable color schemes and chart types

## Troubleshooting

### Issue: "Failed to run sensitivity analysis"
- **Cause**: Missing or invalid simulation data
- **Solution**: Ensure `simulationData` prop contains valid parameter configurations and outputs

### Issue: "Failed to compute correlation matrix"
- **Cause**: Data arrays have different lengths or insufficient samples
- **Solution**: Verify all arrays in `metricsData` have the same length (min 3 samples)

### Issue: "Failed to decompose time series"
- **Cause**: Time series too short for specified period
- **Solution**: Ensure time series length ≥ 2 × period

### Issue: Charts not displaying
- **Cause**: Missing Recharts dependency
- **Solution**: `npm install recharts`

## Support

For issues or questions:
1. Check API endpoint documentation at `/docs`
2. Review backend service implementation
3. Verify authentication and permissions
4. Check browser console for errors

---

**Created**: 2026-01-13
**Phase**: 6 Sprint 2
**Status**: Production Ready
