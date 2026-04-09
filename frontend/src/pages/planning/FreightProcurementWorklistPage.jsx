/**
 * Freight Procurement Worklist Page
 *
 * Dedicated worklist for the Freight Procurement Analyst — human counterpart of the
 * Freight Procurement TRM. The TRM recommends carrier waterfall tendering decisions
 * (TENDER / DEFER / SPOT / BROKER) and the analyst reviews, accepts,
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

const TRM_TYPE = 'freight_procurement';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for recommended action chips */
const ACTION_COLORS = {
  TENDER: 'success',
  DEFER: 'default',
  SPOT: 'warning',
  BROKER: 'info',
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

// ---------------------------------------------------------------------------
// Column definitions for TRMDecisionWorklist
// ---------------------------------------------------------------------------

const COLUMNS = [
  {
    key: 'load_id',
    label: 'Load',
    render: (d) => (
      <Typography variant="body2" fontWeight="medium">
        {d.load_id || '—'}
      </Typography>
    ),
  },
  {
    key: 'lane_id',
    label: 'Lane',
    render: (d) => d.lane_id || '—',
  },
  {
    key: 'mode',
    label: 'Mode',
    render: (d) => d.mode || '—',
  },
  {
    key: 'required_equipment',
    label: 'Equipment',
    render: (d) => d.required_equipment || '—',
  },
  {
    key: 'weight',
    label: 'Weight',
    render: (d) =>
      d.weight != null
        ? `${Number(d.weight).toLocaleString()} lbs`
        : '—',
  },
  {
    key: 'primary_carrier_rate',
    label: 'Primary Rate',
    render: (d) => formatCurrency(d.primary_carrier_rate),
  },
  {
    key: 'dat_benchmark_rate',
    label: 'Benchmark',
    render: (d) => formatCurrency(d.dat_benchmark_rate),
  },
  {
    key: 'tender_attempt',
    label: 'Attempt #',
    render: (d) =>
      d.tender_attempt != null
        ? Number(d.tender_attempt)
        : '—',
  },
  {
    key: 'hours_to_tender_deadline',
    label: 'Hours Left',
    render: (d) => {
      if (d.hours_to_tender_deadline == null) return '—';
      const hours = Number(d.hours_to_tender_deadline);
      const color = hours < 4 ? 'error.main' : hours < 12 ? 'warning.main' : 'text.primary';
      return (
        <Typography variant="body2" sx={{ color, fontWeight: hours < 4 ? 'bold' : 'normal' }}>
          {hours.toFixed(1)}
        </Typography>
      );
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
    key: 'carrier_id',
    label: 'Override Carrier',
    type: 'text',
    helperText: 'Specify an alternative carrier ID',
  },
  {
    key: 'rate_override',
    label: 'Override Rate',
    type: 'number',
    helperText: 'Override rate in dollars',
  },
  {
    key: 'action',
    label: 'Override Action',
    type: 'text',
    options: [
      { value: 'tender', label: 'Tender' },
      { value: 'defer', label: 'Defer' },
      { value: 'spot', label: 'Spot' },
      { value: 'broker', label: 'Broker' },
    ],
    helperText: 'Change the recommended procurement action',
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

  // Avg rate vs benchmark %
  const rateComps = decisions.filter(
    (d) => d.primary_carrier_rate != null && d.dat_benchmark_rate != null && Number(d.dat_benchmark_rate) > 0
  );
  const avgRateVsBenchmark =
    rateComps.length > 0
      ? (
          (rateComps.reduce(
            (sum, d) => sum + Number(d.primary_carrier_rate) / Number(d.dat_benchmark_rate),
            0
          ) /
            rateComps.length) *
          100
        ).toFixed(1)
      : '0.0';

  // Accept rate (TENDER actions)
  const tenderCount = decisions.filter(
    (d) => d.recommended_action === 'TENDER'
  ).length;
  const acceptRate =
    decisions.length > 0
      ? ((tenderCount / decisions.length) * 100).toFixed(1)
      : '0.0';

  // Avg hours to deadline
  const deadlineValues = decisions.filter((d) => d.hours_to_tender_deadline != null);
  const avgHours =
    deadlineValues.length > 0
      ? (deadlineValues.reduce((sum, d) => sum + Number(d.hours_to_tender_deadline), 0) / deadlineValues.length).toFixed(1)
      : '0.0';

  return [
    {
      title: 'Pending Tenders',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'Avg Rate vs Benchmark',
      value: `${avgRateVsBenchmark}%`,
      color: Number(avgRateVsBenchmark) > 110 ? '#d32f2f' : Number(avgRateVsBenchmark) > 100 ? '#ed6c02' : '#2e7d32',
      subtitle: 'Primary rate / benchmark',
    },
    {
      title: 'Accept Rate',
      value: `${acceptRate}%`,
      color: Number(acceptRate) > 70 ? '#2e7d32' : '#ed6c02',
      subtitle: `${tenderCount} of ${decisions.length} decisions`,
    },
    {
      title: 'Avg Hours to Deadline',
      value: avgHours,
      color: Number(avgHours) < 8 ? '#d32f2f' : Number(avgHours) < 24 ? '#ed6c02' : '#2e7d32',
      subtitle: 'Time remaining to tender',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const FreightProcurementWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const location = useLocation();
  const initialStatusFilter = location.state?.filters?.status;
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_freight_procurement_worklist');
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
      <RoleTimeSeries roleKey="freight_procurement" compact className="mb-4" />
      {/* Header */}
      <Box
        display="flex"
        justifyContent="space-between"
        alignItems="center"
        mb={3}
      >
        <Box>
          <Typography variant="h5" gutterBottom>
            Freight Procurement Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review carrier waterfall tendering recommendations from the AI agent.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_freight_procurement_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Freight Procurement Worklist"
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

export default FreightProcurementWorklistPage;
