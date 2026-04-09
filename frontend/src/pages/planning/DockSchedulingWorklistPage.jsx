/**
 * Dock Scheduling Worklist Page
 *
 * Dedicated worklist for the Dock Scheduler — human counterpart of the
 * Dock Scheduling TRM. The TRM recommends appointment and dock door optimization
 * decisions (SCHEDULE / DEFER / EXPEDITE / REJECT) and the scheduler reviews,
 * accepts, overrides, or rejects each recommendation before execution.
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

const TRM_TYPE = 'dock_scheduling';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for recommended action chips */
const ACTION_COLORS = {
  SCHEDULE: 'success',
  DEFER: 'default',
  EXPEDITE: 'warning',
  REJECT: 'error',
};

/** Color mapping for appointment type chips */
const TYPE_COLORS = {
  PICKUP: 'info',
  DELIVERY: 'success',
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
 * Get detention risk label and color from score.
 */
const getDetentionRisk = (score) => {
  if (score == null || isNaN(score)) return { label: '—', color: 'default' };
  if (score < 0.3) return { label: 'Low', color: 'success' };
  if (score < 0.7) return { label: 'Medium', color: 'warning' };
  return { label: 'High', color: 'error' };
};

// ---------------------------------------------------------------------------
// Column definitions for TRMDecisionWorklist
// ---------------------------------------------------------------------------

const COLUMNS = [
  {
    key: 'facility_id',
    label: 'Facility',
    render: (d) => (
      <Typography variant="body2" fontWeight="medium">
        {d.facility_id || '—'}
      </Typography>
    ),
  },
  {
    key: 'appointment_type',
    label: 'Type',
    render: (d) => {
      const type = d.appointment_type || '—';
      return (
        <Chip
          label={type}
          size="small"
          color={TYPE_COLORS[type] || 'default'}
          variant="outlined"
        />
      );
    },
  },
  {
    key: 'requested_time',
    label: 'Requested',
    render: (d) => d.requested_time || '—',
  },
  {
    key: 'earliest_available_slot',
    label: 'Available Slot',
    render: (d) => d.earliest_available_slot || '—',
  },
  {
    key: 'utilization_pct',
    label: 'Door Util %',
    render: (d) => {
      if (d.utilization_pct == null) return '—';
      const val = Number(d.utilization_pct);
      const color = val > 90 ? '#d32f2f' : val > 75 ? '#ed6c02' : '#2e7d32';
      return (
        <Typography variant="body2" sx={{ color, fontWeight: val > 90 ? 'bold' : 'normal' }}>
          {val.toFixed(1)}%
        </Typography>
      );
    },
  },
  {
    key: 'current_queue_depth',
    label: 'Queue',
    render: (d) =>
      d.current_queue_depth != null
        ? Number(d.current_queue_depth).toLocaleString()
        : '—',
  },
  {
    key: 'avg_dwell_time_minutes',
    label: 'Dwell Min',
    render: (d) =>
      d.avg_dwell_time_minutes != null
        ? Number(d.avg_dwell_time_minutes).toFixed(0)
        : '—',
  },
  {
    key: 'detention_risk_score',
    label: 'Detention Risk',
    render: (d) => {
      const risk = getDetentionRisk(d.detention_risk_score);
      return (
        <Chip
          label={risk.label}
          size="small"
          color={risk.color}
          variant="outlined"
        />
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
    key: 'dock_door_id',
    label: 'Dock Door',
    type: 'text',
    helperText: 'Assign specific dock door',
  },
  {
    key: 'appointment_time',
    label: 'Appointment Time',
    type: 'date',
    helperText: 'Override appointment time',
  },
  {
    key: 'priority',
    label: 'Priority',
    type: 'text',
    options: [
      { value: 'expedite', label: 'Expedite' },
      { value: 'standard', label: 'Standard' },
      { value: 'defer', label: 'Defer' },
    ],
    helperText: 'Set scheduling priority',
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
  const appointmentCount = proposed.length;

  // Avg door utilization
  const utilizations = decisions
    .map((d) => Number(d.utilization_pct))
    .filter((v) => !isNaN(v));
  const avgUtil =
    utilizations.length > 0
      ? (utilizations.reduce((s, v) => s + v, 0) / utilizations.length).toFixed(1)
      : '0.0';

  // Avg dwell time
  const dwells = decisions
    .map((d) => Number(d.avg_dwell_time_minutes))
    .filter((v) => !isNaN(v));
  const avgDwell =
    dwells.length > 0
      ? (dwells.reduce((s, v) => s + v, 0) / dwells.length).toFixed(0)
      : '0';

  // Detention risk count (high risk)
  const detentionCount = decisions.filter(
    (d) => d.detention_risk_score != null && Number(d.detention_risk_score) >= 0.7
  ).length;

  return [
    {
      title: 'Appointments Today',
      value: appointmentCount,
      color: appointmentCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${appointmentCount} awaiting scheduling`,
    },
    {
      title: 'Door Utilization %',
      value: `${avgUtil}%`,
      color: Number(avgUtil) > 90 ? '#d32f2f' : '#2e7d32',
      subtitle: 'Average door utilization',
    },
    {
      title: 'Avg Dwell Minutes',
      value: avgDwell,
      color: Number(avgDwell) > 60 ? '#d32f2f' : '#2e7d32',
      subtitle: 'Average dwell time',
    },
    {
      title: 'Detention Risk Count',
      value: detentionCount,
      color: detentionCount > 0 ? '#d32f2f' : '#2e7d32',
      subtitle: `${detentionCount} high detention risk`,
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const DockSchedulingWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const location = useLocation();
  const initialStatusFilter = location.state?.filters?.status;
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_dock_scheduling_worklist');
  const { formatSite, loadLookupsForConfig } = useDisplayPreferences();

  useEffect(() => { loadLookupsForConfig(configId); }, [configId, loadLookupsForConfig]);

  // Memoize columns with display preference resolvers
  const columns = useMemo(() => COLUMNS.map((col) => {
    if (col.key === 'facility_id') {
      return { ...col, render: (d) => (
        <Typography variant="body2" fontWeight="medium">{formatSite(d.facility_id, d.facility_name) || '—'}</Typography>
      )};
    }
    return col;
  }), [formatSite]);

  // Memoize the summary card builder to keep a stable reference
  const summaryCardsFn = useMemo(() => buildSummaryCards, []);

  if (capLoading) {
    return null; // Capabilities still loading; TRMDecisionWorklist shows its own spinner
  }

  return (
    <Box sx={{ p: 3 }}>
      <RoleTimeSeries roleKey="dock_scheduling" compact className="mb-4" />
      {/* Header */}
      <Box
        display="flex"
        justifyContent="space-between"
        alignItems="center"
        mb={3}
      >
        <Box>
          <Typography variant="h5" gutterBottom>
            Dock Scheduling Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review appointment and dock door optimization recommendations from the AI agent.
            Accept, override with reason, or reject each decision before
            execution.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_dock_scheduling_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Dock Scheduling Worklist"
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

export default DockSchedulingWorklistPage;
