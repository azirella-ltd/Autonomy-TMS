/**
 * Capacity Promise Worklist Page
 *
 * Dedicated worklist for the Capacity Promise Analyst — human counterpart of the
 * Capacity Promise TRM. The TRM recommends lane capacity commitment decisions
 * (ACCEPT / DEFER / ESCALATE) and the analyst reviews, accepts,
 * overrides, or rejects each recommendation before execution.
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

const TRM_TYPE = 'capacity_promise';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for recommended action chips */
const ACTION_COLORS = {
  ACCEPT: 'success',
  DEFER: 'default',
  ESCALATE: 'warning',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a number as USD currency.
 */
const formatCurrency = (value) => {
  if (value == null || isNaN(value)) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
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
    key: 'mode',
    label: 'Mode',
    render: (d) => d.mode || '—',
  },
  {
    key: 'requested_date',
    label: 'Requested Date',
    render: (d) => d.requested_date || '—',
  },
  {
    key: 'requested_loads',
    label: 'Requested Loads',
    render: (d) =>
      d.requested_loads != null
        ? Number(d.requested_loads).toLocaleString()
        : '—',
  },
  {
    key: 'available_capacity',
    label: 'Available Capacity',
    render: (d) =>
      d.available_capacity != null
        ? Number(d.available_capacity).toLocaleString()
        : '—',
  },
  {
    key: 'utilization_pct',
    label: 'Utilization %',
    render: (d) => {
      if (d.utilization_pct == null) return '—';
      const pct = (Number(d.utilization_pct) * 100).toFixed(1);
      const color = Number(d.utilization_pct) < 0.7 ? 'success' : Number(d.utilization_pct) < 0.9 ? 'warning' : 'error';
      return <Chip label={`${pct}%`} size="small" color={color} variant="outlined" />;
    },
  },
  {
    key: 'primary_carrier_available',
    label: 'Primary Carrier',
    render: (d) => {
      if (d.primary_carrier_available == null) return '—';
      return (
        <Chip
          label={d.primary_carrier_available ? 'Yes' : 'No'}
          size="small"
          color={d.primary_carrier_available ? 'success' : 'error'}
          variant="outlined"
        />
      );
    },
  },
  {
    key: 'confidence',
    label: 'Confidence',
    render: (d) => formatPercentage(d.confidence),
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
    key: 'available_loads',
    label: 'Override Available Loads',
    type: 'number',
    helperText: 'Override available load count',
  },
  {
    key: 'promised_date',
    label: 'Override Promise Date',
    type: 'date',
    helperText: 'Override promise date',
  },
  {
    key: 'carrier_id',
    label: 'Alternative Carrier',
    type: 'text',
    helperText: 'Specify alternative carrier',
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

  // Avg utilization
  const utilizationValues = decisions.filter((d) => d.utilization_pct != null);
  const avgUtilization =
    utilizationValues.length > 0
      ? ((utilizationValues.reduce((sum, d) => sum + Number(d.utilization_pct), 0) / utilizationValues.length) * 100).toFixed(1)
      : '0.0';

  // Capacity gaps: where available < requested
  const gapCount = decisions.filter(
    (d) => d.available_capacity != null && d.requested_loads != null && Number(d.available_capacity) < Number(d.requested_loads)
  ).length;

  // Promise rate
  const acceptedCount = decisions.filter(
    (d) => d.recommended_action === 'ACCEPT'
  ).length;
  const promiseRate =
    decisions.length > 0
      ? ((acceptedCount / decisions.length) * 100).toFixed(1)
      : '0.0';

  return [
    {
      title: 'Pending Promises',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'Avg Utilization %',
      value: `${avgUtilization}%`,
      color: Number(avgUtilization) > 90 ? '#d32f2f' : Number(avgUtilization) > 70 ? '#ed6c02' : '#2e7d32',
      subtitle: 'Across all lanes',
    },
    {
      title: 'Capacity Gaps',
      value: gapCount,
      color: gapCount > 0 ? '#d32f2f' : '#2e7d32',
      subtitle: `${gapCount} lanes under capacity`,
    },
    {
      title: 'Promise Rate',
      value: `${promiseRate}%`,
      color: Number(promiseRate) > 80 ? '#2e7d32' : '#ed6c02',
      subtitle: `${acceptedCount} of ${decisions.length} decisions`,
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const CapacityPromiseWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const location = useLocation();
  const initialStatusFilter = location.state?.filters?.status;
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_capacity_promise_worklist');
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
      <RoleTimeSeries roleKey="capacity_promise" compact className="mb-4" />
      {/* Header */}
      <Box
        display="flex"
        justifyContent="space-between"
        alignItems="center"
        mb={3}
      >
        <Box>
          <Typography variant="h5" gutterBottom>
            Capacity Promise Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review lane capacity commitment recommendations from the AI agent.
            Accept, override with reason, or reject each decision before execution.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_capacity_promise_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Capacity Promise Worklist"
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

export default CapacityPromiseWorklistPage;
