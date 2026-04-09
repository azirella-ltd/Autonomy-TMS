/**
 * Exception Management Worklist Page
 *
 * Dedicated worklist for the Exception Management Analyst — human counterpart of the
 * Exception Management TRM. The TRM recommends delay, damage, and refusal resolution
 * decisions (RETENDER / REROUTE / PARTIAL_DELIVER / ESCALATE / WRITE_OFF) and the
 * analyst reviews, accepts, overrides, or rejects each recommendation before execution.
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

const TRM_TYPE = 'exception_management';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for recommended action chips */
const ACTION_COLORS = {
  RETENDER: 'warning',
  REROUTE: 'info',
  PARTIAL_DELIVER: 'default',
  ESCALATE: 'error',
  WRITE_OFF: 'error',
};

/** Color mapping for severity chips */
const SEVERITY_COLORS = {
  CRITICAL: 'error',
  HIGH: 'warning',
  MEDIUM: 'info',
  LOW: 'default',
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
    key: 'exception_id',
    label: 'Exception',
    render: (d) => (
      <Typography variant="body2" fontWeight="medium">
        {d.exception_id || '—'}
      </Typography>
    ),
  },
  {
    key: 'shipment_id',
    label: 'Shipment',
    render: (d) => d.shipment_id || '—',
  },
  {
    key: 'exception_type',
    label: 'Type',
    render: (d) => {
      const type = d.exception_type || '—';
      return <Chip label={type} size="small" variant="outlined" />;
    },
  },
  {
    key: 'severity',
    label: 'Severity',
    render: (d) => {
      const severity = d.severity || '—';
      return (
        <Chip
          label={severity}
          size="small"
          color={SEVERITY_COLORS[severity] || 'default'}
          variant={severity === 'CRITICAL' ? 'filled' : 'outlined'}
        />
      );
    },
  },
  {
    key: 'hours_since_detected',
    label: 'Hours Open',
    render: (d) =>
      d.hours_since_detected != null
        ? Number(d.hours_since_detected).toFixed(1)
        : '—',
  },
  {
    key: 'estimated_delay_hrs',
    label: 'Est. Delay',
    render: (d) =>
      d.estimated_delay_hrs != null
        ? `${Number(d.estimated_delay_hrs).toFixed(1)} hrs`
        : '—',
  },
  {
    key: 'estimated_cost_impact',
    label: 'Cost Impact',
    render: (d) => formatCurrency(d.estimated_cost_impact),
  },
  {
    key: 'recommended_action',
    label: 'Resolution',
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
    key: 'resolution_action',
    label: 'Resolution Action',
    type: 'text',
    options: [
      { value: 'retender', label: 'Retender' },
      { value: 'reroute', label: 'Reroute' },
      { value: 'partial_deliver', label: 'Partial Deliver' },
      { value: 'escalate', label: 'Escalate' },
      { value: 'write_off', label: 'Write Off' },
    ],
    helperText: 'Select an alternative resolution action',
  },
  {
    key: 'cost_authorization',
    label: 'Cost Authorization',
    type: 'number',
    helperText: 'Maximum cost authorization in dollars',
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
  const openCount = decisions.length;

  // Critical count
  const criticalCount = decisions.filter(
    (d) => d.severity === 'CRITICAL'
  ).length;

  // Avg resolution hours
  const hoursValues = decisions.filter((d) => d.hours_since_detected != null);
  const avgHours =
    hoursValues.length > 0
      ? (hoursValues.reduce((sum, d) => sum + Number(d.hours_since_detected), 0) / hoursValues.length).toFixed(1)
      : '0.0';

  // Total cost impact
  const totalCost = decisions.reduce(
    (sum, d) => sum + (Number(d.estimated_cost_impact) || 0),
    0
  );

  return [
    {
      title: 'Open Exceptions',
      value: openCount,
      color: openCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${openCount} requiring action`,
    },
    {
      title: 'Critical Count',
      value: criticalCount,
      color: criticalCount > 0 ? '#d32f2f' : '#2e7d32',
      subtitle: `${criticalCount} critical severity`,
    },
    {
      title: 'Avg Resolution Hours',
      value: avgHours,
      color: Number(avgHours) > 24 ? '#d32f2f' : Number(avgHours) > 8 ? '#ed6c02' : '#2e7d32',
      subtitle: 'Hours since detection',
    },
    {
      title: 'Total Cost Impact',
      value: formatCurrency(totalCost),
      color: totalCost > 50000 ? '#d32f2f' : totalCost > 10000 ? '#ed6c02' : '#1565c0',
      subtitle: 'Estimated financial impact',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const ExceptionMgmtWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const location = useLocation();
  const initialStatusFilter = location.state?.filters?.status;
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_exception_mgmt_worklist');
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
      <RoleTimeSeries roleKey="exception_management" compact className="mb-4" />
      {/* Header */}
      <Box
        display="flex"
        justifyContent="space-between"
        alignItems="center"
        mb={3}
      >
        <Box>
          <Typography variant="h5" gutterBottom>
            Exception Management Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review delay, damage, and refusal resolution recommendations from the AI agent.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_exception_mgmt_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Exception Management Worklist"
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

export default ExceptionMgmtWorklistPage;
