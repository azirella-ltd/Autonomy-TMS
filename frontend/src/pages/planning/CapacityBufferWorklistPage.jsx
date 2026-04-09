/**
 * Capacity Buffer Worklist Page
 *
 * Dedicated worklist for the Capacity Buffer Analyst — human counterpart of the
 * Capacity Buffer TRM. The TRM recommends reserve carrier capacity decisions
 * and the analyst reviews, accepts, overrides, or rejects each recommendation
 * before execution.
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

const TRM_TYPE = 'capacity_buffer';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for recommended action chips */
const ACTION_COLORS = {
  INCREASE: 'warning',
  MAINTAIN: 'success',
  DECREASE: 'info',
  RELEASE: 'default',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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
    key: 'mode',
    label: 'Mode',
    render: (d) => d.mode || '—',
  },
  {
    key: 'forecast_loads',
    label: 'Forecast Loads',
    render: (d) =>
      d.forecast_loads != null
        ? Number(d.forecast_loads).toLocaleString()
        : '—',
  },
  {
    key: 'buffer_loads',
    label: 'Buffer Loads',
    render: (d) =>
      d.buffer_loads != null
        ? Number(d.buffer_loads).toLocaleString()
        : '—',
  },
  {
    key: 'buffer_policy',
    label: 'Policy',
    render: (d) => {
      const policy = d.buffer_policy || '—';
      return <Chip label={policy} size="small" variant="outlined" />;
    },
  },
  {
    key: 'recent_tender_reject_rate',
    label: 'Reject Rate %',
    render: (d) => {
      if (d.recent_tender_reject_rate == null) return '—';
      const pct = (Number(d.recent_tender_reject_rate) * 100).toFixed(1);
      const color = Number(d.recent_tender_reject_rate) < 0.1 ? 'success' : Number(d.recent_tender_reject_rate) < 0.2 ? 'warning' : 'error';
      return <Chip label={`${pct}%`} size="small" color={color} variant="outlined" />;
    },
  },
  {
    key: 'avg_spot_premium_pct',
    label: 'Spot Premium %',
    render: (d) => {
      if (d.avg_spot_premium_pct == null) return '—';
      const pct = (Number(d.avg_spot_premium_pct) * 100).toFixed(1);
      return `${pct}%`;
    },
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
    key: 'buffer_loads',
    label: 'Override Buffer Loads',
    type: 'number',
    helperText: 'Override the recommended buffer load count',
  },
  {
    key: 'buffer_policy',
    label: 'Buffer Policy',
    type: 'text',
    options: [
      { value: 'fixed', label: 'Fixed' },
      { value: 'pct_forecast', label: '% of Forecast' },
      { value: 'conformal', label: 'Conformal' },
    ],
    helperText: 'Select the buffer policy method',
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
  // Lanes with buffer > 0
  const bufferedCount = decisions.filter(
    (d) => d.buffer_loads != null && Number(d.buffer_loads) > 0
  ).length;

  // Avg buffer %
  const bufferPctValues = decisions.filter(
    (d) => d.buffer_loads != null && d.forecast_loads != null && Number(d.forecast_loads) > 0
  );
  const avgBufferPct =
    bufferPctValues.length > 0
      ? (
          (bufferPctValues.reduce(
            (sum, d) => sum + Number(d.buffer_loads) / Number(d.forecast_loads),
            0
          ) /
            bufferPctValues.length) *
          100
        ).toFixed(1)
      : '0.0';

  // Capacity gaps (where buffer is 0 but reject rate is high)
  const gapCount = decisions.filter(
    (d) =>
      (d.buffer_loads == null || Number(d.buffer_loads) === 0) &&
      d.recent_tender_reject_rate != null &&
      Number(d.recent_tender_reject_rate) > 0.1
  ).length;

  // Avg tender reject rate
  const rejectValues = decisions.filter((d) => d.recent_tender_reject_rate != null);
  const avgRejectRate =
    rejectValues.length > 0
      ? (
          (rejectValues.reduce((sum, d) => sum + Number(d.recent_tender_reject_rate), 0) /
            rejectValues.length) *
          100
        ).toFixed(1)
      : '0.0';

  return [
    {
      title: 'Lanes Buffered',
      value: bufferedCount,
      color: '#1565c0',
      subtitle: `${bufferedCount} of ${decisions.length} lanes`,
    },
    {
      title: 'Avg Buffer %',
      value: `${avgBufferPct}%`,
      color: Number(avgBufferPct) > 30 ? '#ed6c02' : '#1565c0',
      subtitle: 'Buffer as % of forecast',
    },
    {
      title: 'Capacity Gaps',
      value: gapCount,
      color: gapCount > 0 ? '#d32f2f' : '#2e7d32',
      subtitle: `${gapCount} unbuffered high-reject lanes`,
    },
    {
      title: 'Tender Reject Rate',
      value: `${avgRejectRate}%`,
      color: Number(avgRejectRate) > 15 ? '#d32f2f' : Number(avgRejectRate) > 10 ? '#ed6c02' : '#2e7d32',
      subtitle: 'Avg across all lanes',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const CapacityBufferWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const location = useLocation();
  const initialStatusFilter = location.state?.filters?.status;
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_capacity_buffer_worklist');
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
      <RoleTimeSeries roleKey="capacity_buffer" compact className="mb-4" />
      {/* Header */}
      <Box
        display="flex"
        justifyContent="space-between"
        alignItems="center"
        mb={3}
      >
        <Box>
          <Typography variant="h5" gutterBottom>
            Capacity Buffer Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review reserve carrier capacity recommendations from the AI agent.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_capacity_buffer_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Capacity Buffer Worklist"
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

export default CapacityBufferWorklistPage;
