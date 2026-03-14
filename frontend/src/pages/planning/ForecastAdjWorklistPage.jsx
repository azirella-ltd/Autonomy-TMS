/**
 * Forecast Adjustment Worklist Page
 *
 * Dedicated worklist for the Demand Planner — human counterpart of the
 * Forecast Adjustment TRM. The TRM recommends signal-driven forecast
 * adjustments (UP / DOWN) and the planner reviews, accepts, overrides,
 * or rejects each recommendation before execution.
 *
 * Override reasons and values are recorded to the TRM replay buffer
 * (is_expert=True) for reinforcement learning.
 */
import React, { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import { Box, Typography, Chip, Alert, Tooltip as MuiTooltip } from '@mui/material';

import TRMDecisionWorklist from '../../components/cascade/TRMDecisionWorklist';
import LayerModeIndicator from '../../components/cascade/LayerModeIndicator';
import { getTRMDecisions, submitTRMAction } from '../../services/planningCascadeApi';
import { useCapabilities } from '../../hooks/useCapabilities';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TRM_TYPE = 'forecast_adjustment';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for adjustment direction chips */
const DIRECTION_COLORS = {
  up: 'warning',
  down: 'info',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a value as a percentage with one decimal.
 */
const formatAdjPercent = (value) => {
  if (value == null || isNaN(value)) return '—';
  return `${Number(value).toFixed(1)}%`;
};

/**
 * Format a number with locale formatting.
 */
const formatNumber = (value) => {
  if (value == null || isNaN(value)) return '—';
  return Number(value).toLocaleString();
};

// ---------------------------------------------------------------------------
// Column definitions for TRMDecisionWorklist
// ---------------------------------------------------------------------------

const FORECAST_ADJ_COLUMNS = [
  {
    key: 'product_id',
    label: 'Product',
    render: (d) => (
      <Typography variant="body2" fontWeight="medium">
        {d.product_id || '—'}
      </Typography>
    ),
  },
  {
    key: 'site_id',
    label: 'Site',
    render: (d) => d.site_id || '—',
  },
  {
    key: 'signal_type',
    label: 'Signal',
    render: (d) => {
      const signal = d.signal_type || '—';
      return (
        <Chip
          label={signal}
          size="small"
          variant="outlined"
        />
      );
    },
  },
  {
    key: 'adjustment_direction',
    label: 'Direction',
    render: (d) => {
      const direction = d.adjustment_direction || '—';
      return (
        <Chip
          label={direction}
          size="small"
          color={DIRECTION_COLORS[direction] || 'default'}
          variant="filled"
        />
      );
    },
  },
  {
    key: 'adjustment_pct',
    label: 'Adj %',
    render: (d) => formatAdjPercent(d.adjustment_pct),
  },
  {
    key: 'current_forecast_value',
    label: 'Current',
    render: (d) => formatNumber(d.current_forecast_value),
  },
  {
    key: 'adjusted_forecast_value',
    label: 'Adjusted',
    render: (d) => formatNumber(d.adjusted_forecast_value),
  },
  {
    key: 'confidence',
    label: 'Confidence',
    render: (d) => {
      if (d.confidence == null) return '—';
      const pct = (d.confidence * 100).toFixed(1);
      const color = d.confidence >= 0.8 ? 'success' : d.confidence >= 0.5 ? 'warning' : 'error';
      return (
        <MuiTooltip title={`Agent confidence: ${pct}%`} arrow>
          <Chip label={`${pct}%`} size="small" color={color} variant="outlined" />
        </MuiTooltip>
      );
    },
  },
];

// ---------------------------------------------------------------------------
// Override field definitions for the Override Dialog
// ---------------------------------------------------------------------------

const FORECAST_ADJ_OVERRIDE_FIELDS = [
  {
    key: 'adjustment_pct',
    label: 'Override Adjustment %',
    type: 'number',
    helperText: 'Enter a new adjustment percentage to replace the agent recommendation',
  },
  {
    key: 'adjustment_direction',
    label: 'Override Direction',
    type: 'text',
    options: [
      { value: 'up', label: 'Up' },
      { value: 'down', label: 'Down' },
    ],
    helperText: 'Change the adjustment direction (up, down)',
  },
  {
    key: 'adjusted_forecast_value',
    label: 'Override Forecast Value',
    type: 'number',
    helperText: 'Enter a specific adjusted forecast value',
  },
];

// ---------------------------------------------------------------------------
// Summary cards builder
// ---------------------------------------------------------------------------

/**
 * Build summary card data from the current set of decisions.
 * Returns an array of { title, value, color?, subtitle? } objects.
 */
const buildSummaryCards = (decisions) => {
  const proposed = decisions.filter((d) => d.status === 'INFORMED');
  const pendingCount = proposed.length;

  // Average adjustment percentage
  const adjPcts = decisions
    .filter((d) => d.adjustment_pct != null && !isNaN(d.adjustment_pct))
    .map((d) => Number(d.adjustment_pct));
  const avgAdjPct =
    adjPcts.length > 0
      ? (adjPcts.reduce((sum, p) => sum + p, 0) / adjPcts.length).toFixed(1)
      : '0.0';

  // Up vs Down ratio
  const upCount = decisions.filter(
    (d) => d.adjustment_direction === 'up'
  ).length;
  const downCount = decisions.filter(
    (d) => d.adjustment_direction === 'down'
  ).length;

  // Override rate: fraction with status OVERRIDDEN
  const overriddenCount = decisions.filter(
    (d) => d.status === 'OVERRIDDEN'
  ).length;
  const overrideRate =
    decisions.length > 0
      ? ((overriddenCount / decisions.length) * 100).toFixed(1)
      : '0.0';

  return [
    {
      title: 'Pending Adjustments',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'Avg Adjustment',
      value: `${avgAdjPct}%`,
      color: Number(avgAdjPct) > 20 ? '#d32f2f' : '#1565c0',
      subtitle: `Across ${adjPcts.length} adjustments`,
    },
    {
      title: 'Up vs Down',
      value: `${upCount} / ${downCount}`,
      color: '#1565c0',
      subtitle: `${upCount} increases, ${downCount} decreases`,
    },
    {
      title: 'Override Rate',
      value: `${overrideRate}%`,
      color: Number(overrideRate) > 25 ? '#ed6c02' : '#2e7d32',
      subtitle: `${overriddenCount} of ${decisions.length} decisions`,
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const ForecastAdjWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const location = useLocation();
  const initialStatusFilter = location.state?.filters?.status;
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_forecast_adj_worklist');

  // Memoize the summary card builder to keep a stable reference
  const summaryCardsFn = useMemo(() => buildSummaryCards, []);

  if (capLoading) {
    return null; // Capabilities still loading; TRMDecisionWorklist shows its own spinner
  }

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box
        display="flex"
        justifyContent="space-between"
        alignItems="center"
        mb={3}
      >
        <Box>
          <Typography variant="h5" gutterBottom>
            Forecast Adjustment Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review signal-driven forecast adjustment recommendations from the
            Forecast Adjustment agent. Accept, override with reason, or reject
            each decision before execution.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Tenant Admin
          to request the <strong>manage_forecast_adj_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Forecast Adjustment Worklist"
        columns={FORECAST_ADJ_COLUMNS}
        overrideFields={FORECAST_ADJ_OVERRIDE_FIELDS}
        summaryCards={summaryCardsFn}
        fetchDecisions={getTRMDecisions}
        submitAction={submitTRMAction}
        canManage={canManage}
        initialStatusFilter={initialStatusFilter}
      />
    </Box>
  );
};

export default ForecastAdjWorklistPage;
