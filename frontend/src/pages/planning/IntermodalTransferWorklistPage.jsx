/**
 * Intermodal Transfer Worklist Page
 *
 * Dedicated worklist for the Intermodal Coordinator — human counterpart of the
 * Intermodal Transfer TRM. The TRM recommends cross-mode transfer decisions
 * (MODE_SHIFT / HOLD / DEFER) and the coordinator reviews, accepts,
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

const TRM_TYPE = 'intermodal_transfer';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for recommended action chips */
const ACTION_COLORS = {
  MODE_SHIFT: 'success',
  HOLD: 'default',
  DEFER: 'info',
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
    key: 'shipment_id',
    label: 'Shipment',
    render: (d) => (
      <Typography variant="body2" fontWeight="medium">
        {d.shipment_id || '—'}
      </Typography>
    ),
  },
  {
    key: 'current_mode',
    label: 'Current Mode',
    render: (d) => {
      const mode = d.current_mode || '—';
      return <Chip label={mode} size="small" variant="outlined" />;
    },
  },
  {
    key: 'candidate_mode',
    label: 'Candidate Mode',
    render: (d) => {
      const mode = d.candidate_mode || '—';
      return <Chip label={mode} size="small" color="info" variant="outlined" />;
    },
  },
  {
    key: 'cost_savings_pct',
    label: 'Cost Savings %',
    render: (d) => {
      if (d.cost_savings_pct == null) return '—';
      const val = Number(d.cost_savings_pct);
      return (
        <Typography variant="body2" sx={{ color: '#2e7d32', fontWeight: val > 10 ? 'bold' : 'normal' }}>
          {val.toFixed(1)}%
        </Typography>
      );
    },
  },
  {
    key: 'transit_time_penalty_days',
    label: 'Transit Penalty',
    render: (d) => {
      if (d.transit_time_penalty_days == null) return '—';
      const val = Number(d.transit_time_penalty_days);
      const color = val > 2 ? '#d32f2f' : val > 1 ? '#ed6c02' : '#2e7d32';
      return (
        <Typography variant="body2" sx={{ color }}>
          {val.toFixed(1)} days
        </Typography>
      );
    },
  },
  {
    key: 'rail_capacity_available',
    label: 'Rail Available',
    render: (d) => (
      <Chip
        label={d.rail_capacity_available ? 'Yes' : 'No'}
        size="small"
        color={d.rail_capacity_available ? 'success' : 'default'}
        variant="outlined"
      />
    ),
  },
  {
    key: 'intermodal_reliability_pct',
    label: 'Reliability %',
    render: (d) => {
      if (d.intermodal_reliability_pct == null) return '—';
      const val = Number(d.intermodal_reliability_pct);
      return `${val.toFixed(1)}%`;
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
    key: 'target_mode',
    label: 'Target Mode',
    type: 'text',
    options: [
      { value: 'road', label: 'Road' },
      { value: 'rail', label: 'Rail' },
      { value: 'ocean', label: 'Ocean' },
      { value: 'air', label: 'Air' },
    ],
    helperText: 'Override the target transportation mode',
  },
  {
    key: 'accept_transit_penalty',
    label: 'Accept Transit Penalty',
    type: 'text',
    options: [
      { value: 'yes', label: 'Yes' },
      { value: 'no', label: 'No' },
    ],
    helperText: 'Accept additional transit time for cost savings',
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
  const modeShiftCount = decisions.filter(
    (d) => d.recommended_action === 'MODE_SHIFT'
  ).length;

  // Avg cost savings %
  const savings = decisions
    .map((d) => Number(d.cost_savings_pct))
    .filter((v) => !isNaN(v));
  const avgSavings =
    savings.length > 0
      ? (savings.reduce((s, v) => s + v, 0) / savings.length).toFixed(1)
      : '0.0';

  // Rail capacity available count
  const railAvailable = decisions.filter(
    (d) => d.rail_capacity_available
  ).length;

  // Avg reliability
  const reliabilities = decisions
    .map((d) => Number(d.intermodal_reliability_pct))
    .filter((v) => !isNaN(v));
  const avgReliability =
    reliabilities.length > 0
      ? (reliabilities.reduce((s, v) => s + v, 0) / reliabilities.length).toFixed(1)
      : '0.0';

  return [
    {
      title: 'Mode Shift Opportunities',
      value: modeShiftCount,
      color: modeShiftCount > 0 ? '#1565c0' : '#2e7d32',
      subtitle: `${modeShiftCount} recommended shifts`,
    },
    {
      title: 'Avg Cost Savings %',
      value: `${avgSavings}%`,
      color: '#2e7d32',
      subtitle: 'Average savings from mode shift',
    },
    {
      title: 'Rail Capacity',
      value: railAvailable,
      color: railAvailable > 0 ? '#2e7d32' : '#d32f2f',
      subtitle: `${railAvailable} with rail available`,
    },
    {
      title: 'Avg Reliability',
      value: `${avgReliability}%`,
      color: Number(avgReliability) < 85 ? '#d32f2f' : '#2e7d32',
      subtitle: 'Intermodal reliability score',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const IntermodalTransferWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const location = useLocation();
  const initialStatusFilter = location.state?.filters?.status;
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_intermodal_transfer_worklist');
  const { formatSite, loadLookupsForConfig } = useDisplayPreferences();

  useEffect(() => { loadLookupsForConfig(configId); }, [configId, loadLookupsForConfig]);

  // Memoize columns with display preference resolvers
  const columns = useMemo(() => COLUMNS.map((col) => {
    if (col.key === 'shipment_id') {
      return { ...col, render: (d) => (
        <Typography variant="body2" fontWeight="medium">{d.shipment_id || '—'}</Typography>
      )};
    }
    return col;
  }), []);

  // Memoize the summary card builder to keep a stable reference
  const summaryCardsFn = useMemo(() => buildSummaryCards, []);

  if (capLoading) {
    return null; // Capabilities still loading; TRMDecisionWorklist shows its own spinner
  }

  return (
    <Box sx={{ p: 3 }}>
      <RoleTimeSeries roleKey="intermodal_transfer" compact className="mb-4" />
      {/* Header */}
      <Box
        display="flex"
        justifyContent="space-between"
        alignItems="center"
        mb={3}
      >
        <Box>
          <Typography variant="h5" gutterBottom>
            Intermodal Transfer Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review cross-mode transfer decisions from the AI agent.
            Accept, override with reason, or reject each decision before
            execution.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_intermodal_transfer_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Intermodal Transfer Worklist"
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

export default IntermodalTransferWorklistPage;
