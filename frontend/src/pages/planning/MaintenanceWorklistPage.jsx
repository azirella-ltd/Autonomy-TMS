/**
 * Maintenance Scheduling Worklist Page
 *
 * Dedicated worklist for the Maintenance Planner — human counterpart of the
 * Maintenance Scheduling TRM. The TRM recommends maintenance scheduling decisions
 * (SCHEDULE / DEFER / EXPEDITE / OUTSOURCE) and the planner reviews, accepts,
 * overrides, or rejects each recommendation before execution.
 *
 * Override reasons and values are recorded to the TRM replay buffer
 * (is_expert=True) for reinforcement learning.
 */
import React, { useMemo } from 'react';
import { Box, Typography, Chip, Alert, Tooltip as MuiTooltip } from '@mui/material';

import TRMDecisionWorklist from '../../components/cascade/TRMDecisionWorklist';
import LayerModeIndicator from '../../components/cascade/LayerModeIndicator';
import { getTRMDecisions, submitTRMAction } from '../../services/planningCascadeApi';
import { useCapabilities } from '../../hooks/useCapabilities';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TRM_TYPE = 'maintenance_scheduling';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for decision type chips */
const DECISION_COLORS = {
  schedule: 'success',
  defer: 'default',
  expedite: 'warning',
  outsource: 'info',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format downtime hours.
 */
const formatDowntime = (value) => {
  if (value == null || isNaN(value)) return '—';
  return `${Number(value).toFixed(1)}h`;
};

// ---------------------------------------------------------------------------
// Column definitions for TRMDecisionWorklist
// ---------------------------------------------------------------------------

const MAINTENANCE_COLUMNS = [
  {
    key: 'asset_id',
    label: 'Asset',
    render: (d) => (
      <Typography variant="body2" fontWeight="medium">
        {d.asset_id || '—'}
      </Typography>
    ),
  },
  {
    key: 'site_id',
    label: 'Site',
    render: (d) => d.site_id || '—',
  },
  {
    key: 'maintenance_order_id',
    label: 'WO #',
    render: (d) => d.maintenance_order_id || '—',
  },
  {
    key: 'maintenance_type',
    label: 'Type',
    render: (d) => d.maintenance_type || '—',
  },
  {
    key: 'decision_type',
    label: 'Decision',
    render: (d) => {
      const decision = d.decision_type || '—';
      return (
        <Chip
          label={decision}
          size="small"
          color={DECISION_COLORS[decision] || 'default'}
          variant="filled"
        />
      );
    },
  },
  {
    key: 'estimated_downtime_hours',
    label: 'Downtime',
    render: (d) => formatDowntime(d.estimated_downtime_hours),
  },
  {
    key: 'priority',
    label: 'Priority',
    render: (d) => d.priority || '—',
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

const MAINTENANCE_OVERRIDE_FIELDS = [
  {
    key: 'decision_type',
    label: 'Override Decision',
    type: 'text',
    options: [
      { value: 'schedule', label: 'Schedule' },
      { value: 'defer', label: 'Defer' },
      { value: 'expedite', label: 'Expedite' },
      { value: 'outsource', label: 'Outsource' },
    ],
    helperText: 'Change the recommended decision (schedule, defer, expedite, outsource)',
  },
  {
    key: 'scheduled_date',
    label: 'Override Scheduled Date',
    type: 'text',
    helperText: 'Enter a new scheduled date (YYYY-MM-DD)',
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
  const proposed = decisions.filter((d) => d.status === 'PROPOSED');
  const pendingCount = proposed.length;

  // Total downtime hours across proposed WOs
  const totalDowntime = proposed.reduce(
    (sum, d) => sum + (Number(d.estimated_downtime_hours) || 0),
    0
  );

  // Deferred rate: fraction of all decisions that are defer
  const deferredCount = decisions.filter(
    (d) => d.decision_type === 'defer'
  ).length;
  const deferredRate =
    decisions.length > 0
      ? ((deferredCount / decisions.length) * 100).toFixed(1)
      : '0.0';

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
      title: 'Pending WOs',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'Total Downtime',
      value: `${totalDowntime.toFixed(1)}h`,
      color: totalDowntime > 24 ? '#d32f2f' : '#1565c0',
      subtitle: 'Estimated hours',
    },
    {
      title: 'Deferred',
      value: `${deferredRate}%`,
      color: Number(deferredRate) > 30 ? '#d32f2f' : '#2e7d32',
      subtitle: `${deferredCount} of ${decisions.length} decisions`,
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

const MaintenanceWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_maintenance_worklist');

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
            Maintenance Scheduling Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review maintenance scheduling recommendations from the maintenance scheduling agent.
            Accept, override with reason, or reject each decision before
            execution.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Tenant Admin
          to request the <strong>manage_maintenance_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Maintenance Scheduling Worklist"
        columns={MAINTENANCE_COLUMNS}
        overrideFields={MAINTENANCE_OVERRIDE_FIELDS}
        summaryCards={summaryCardsFn}
        fetchDecisions={getTRMDecisions}
        submitAction={submitTRMAction}
        canManage={canManage}
      />
    </Box>
  );
};

export default MaintenanceWorklistPage;
