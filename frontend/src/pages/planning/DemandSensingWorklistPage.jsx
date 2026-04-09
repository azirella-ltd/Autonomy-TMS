/**
 * Demand Sensing Worklist Page
 *
 * Dedicated worklist for the Demand Sensing Analyst — human counterpart of the
 * Demand Sensing TRM. The TRM recommends shipping volume forecast adjustment
 * decisions and the analyst reviews, accepts, overrides, or rejects each
 * recommendation before execution.
 *
 * Override reasons and values are recorded to the TRM replay buffer
 * (is_expert=True) for reinforcement learning.
 */
import React, { useMemo, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { Box, Typography, Chip, Alert, Tooltip as MuiTooltip } from '@mui/material';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';

import TRMDecisionWorklist from '../../components/cascade/TRMDecisionWorklist';
import LayerModeIndicator from '../../components/cascade/LayerModeIndicator';
import { getTRMDecisions, submitTRMAction } from '../../services/planningCascadeApi';
import { useCapabilities } from '../../hooks/useCapabilities';
import RoleTimeSeries from '../../components/charts/RoleTimeSeries';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TRM_TYPE = 'demand_sensing';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for recommended action chips */
const ACTION_COLORS = {
  ADJUST_UP: 'warning',
  ADJUST_DOWN: 'info',
  ACCEPT: 'success',
  DEFER: 'default',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a number as a signed adjustment string.
 */
const formatAdjustment = (value) => {
  if (value == null || isNaN(value)) return '—';
  const num = Number(value);
  const sign = num >= 0 ? '+' : '';
  return `${sign}${num.toLocaleString()}`;
};

/**
 * Format a decimal as a percentage string.
 */
const formatPercentage = (value) => {
  if (value == null || isNaN(value)) return '—';
  return `${(Number(value) * 100).toFixed(1)}%`;
};

// ---------------------------------------------------------------------------
// Column definitions for TRMDecisionWorklist
// ---------------------------------------------------------------------------

const COLUMNS = [
  {
    key: 'lane_id',
    label: 'Lane',
    render: (d) => (
      <Typography variant="body2" fontWeight="medium">
        {d.lane_id || '—'}
      </Typography>
    ),
  },
  {
    key: 'period_start',
    label: 'Period',
    render: (d) => d.period_start || '—',
  },
  {
    key: 'forecast_loads',
    label: 'Current Forecast',
    render: (d) =>
      d.forecast_loads != null
        ? Number(d.forecast_loads).toLocaleString()
        : '—',
  },
  {
    key: 'adjustment',
    label: 'Proposed Adjustment',
    render: (d) => {
      if (d.adjustment == null) return '—';
      const num = Number(d.adjustment);
      const color = num > 0 ? 'warning.main' : num < 0 ? 'info.main' : 'text.primary';
      return (
        <Typography variant="body2" sx={{ color, fontWeight: 'medium' }}>
          {formatAdjustment(d.adjustment)}
        </Typography>
      );
    },
  },
  {
    key: 'signal_type',
    label: 'Signal',
    render: (d) => {
      const signal = d.signal_type || '—';
      return <Chip label={signal} size="small" variant="outlined" />;
    },
  },
  {
    key: 'signal_confidence',
    label: 'Signal Confidence',
    render: (d) => formatPercentage(d.signal_confidence),
  },
  {
    key: 'forecast_mape',
    label: 'MAPE %',
    render: (d) =>
      d.forecast_mape != null
        ? `${Number(d.forecast_mape).toFixed(1)}%`
        : '—',
  },
  {
    key: 'recommended_action',
    label: 'Action',
    render: (d) => {
      const action = d.recommended_action || '—';
      return (
        <Chip
          label={action}
          size="small"
          color={ACTION_COLORS[action] || 'default'}
          variant="filled"
        />
      );
    },
  },
];

// ---------------------------------------------------------------------------
// Override field definitions for the Override Dialog
// ---------------------------------------------------------------------------

const OVERRIDE_FIELDS = [
  {
    key: 'adjusted_forecast_loads',
    label: 'Override Forecast Loads',
    type: 'number',
    helperText: 'Enter the adjusted forecast load count',
  },
  {
    key: 'adjustment_reason',
    label: 'Adjustment Reason',
    type: 'text',
    options: [
      { value: 'seasonal_shift', label: 'Seasonal Shift' },
      { value: 'volume_surge', label: 'Volume Surge' },
      { value: 'volume_drop', label: 'Volume Drop' },
      { value: 'signal_override', label: 'Signal Override' },
      { value: 'market_intelligence', label: 'Market Intelligence' },
    ],
    helperText: 'Select the reason for the forecast adjustment',
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

  // Avg adjustment %
  const adjustmentValues = decisions.filter(
    (d) => d.adjustment != null && d.forecast_loads != null && Number(d.forecast_loads) > 0
  );
  const avgAdjustmentPct =
    adjustmentValues.length > 0
      ? (
          (adjustmentValues.reduce(
            (sum, d) => sum + Math.abs(Number(d.adjustment)) / Number(d.forecast_loads),
            0
          ) /
            adjustmentValues.length) *
          100
        ).toFixed(1)
      : '0.0';

  // Active signals
  const activeSignals = decisions.filter(
    (d) => d.signal_type != null && d.signal_type !== ''
  ).length;

  // Avg MAPE
  const mapeValues = decisions.filter((d) => d.forecast_mape != null);
  const avgMape =
    mapeValues.length > 0
      ? (mapeValues.reduce((sum, d) => sum + Number(d.forecast_mape), 0) / mapeValues.length).toFixed(1)
      : '0.0';

  return [
    {
      title: 'Pending Adjustments',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'Avg Adjustment %',
      value: `${avgAdjustmentPct}%`,
      color: Number(avgAdjustmentPct) > 20 ? '#d32f2f' : '#1565c0',
      subtitle: 'Mean absolute adjustment',
    },
    {
      title: 'Active Signals',
      value: activeSignals,
      color: '#1565c0',
      subtitle: `${activeSignals} signals detected`,
    },
    {
      title: 'Avg MAPE',
      value: `${avgMape}%`,
      color: Number(avgMape) > 15 ? '#d32f2f' : Number(avgMape) > 10 ? '#ed6c02' : '#2e7d32',
      subtitle: 'Forecast accuracy',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const DemandSensingWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const location = useLocation();
  const initialStatusFilter = location.state?.filters?.status;
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_demand_sensing_worklist');
  const { loadLookupsForConfig } = useDisplayPreferences();

  useEffect(() => { loadLookupsForConfig(configId); }, [configId, loadLookupsForConfig]);

  // Memoize columns
  const columns = useMemo(() => COLUMNS, []);

  // Memoize the summary card builder to keep a stable reference
  const summaryCardsFn = useMemo(() => buildSummaryCards, []);

  if (capLoading) {
    return null;
  }

  return (
    <Box sx={{ p: 3 }}>
      <RoleTimeSeries roleKey="demand_sensing" compact className="mb-4" />
      {/* Header */}
      <Box
        display="flex"
        justifyContent="space-between"
        alignItems="center"
        mb={3}
      >
        <Box>
          <Typography variant="h5" gutterBottom>
            Demand Sensing Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review shipping volume forecast adjustment recommendations from the AI agent.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_demand_sensing_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Demand Sensing Worklist"
        columns={columns}
        overrideFields={OVERRIDE_FIELDS}
        summaryCards={summaryCardsFn}
        fetchDecisions={getTRMDecisions}
        submitAction={submitTRMAction}
        canManage={canManage}
        initialStatusFilter={initialStatusFilter}
      />
    </Box>
  );
};

export default DemandSensingWorklistPage;
