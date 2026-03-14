/**
 * Order Tracking Worklist Page
 *
 * Dedicated worklist for the Order Tracking Analyst — the human counterpart
 * of the Order Tracking TRM. This TRM detects order exceptions (LATE_DELIVERY,
 * QUANTITY_SHORTAGE, QUALITY_ISSUE, etc.) and recommends remediation actions
 * (EXPEDITE, FIND_ALTERNATE, ESCALATE, CANCEL_REORDER, etc.).
 *
 * Uses the AI-as-Labor worklist pattern: the TRM agent proposes exception
 * resolutions, the analyst reviews via Accept / Override / Reject.
 * Override reasons are captured for RL training (is_expert=True).
 *
 * Adaptive Decision Hierarchy: OrderTrackingTRM is a VFA (Value Function Approximation)
 * agent — narrow scope, per-order exception detection and recommended actions.
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

const ORDER_TYPE_COLORS = {
  PO: 'primary',
  TO: 'secondary',
  Customer: 'success',
  Production: 'warning',
};

const SEVERITY_COLORS = {
  INFO: 'info',
  WARNING: 'warning',
  HIGH: 'error',
  CRITICAL: 'error',
};

const SEVERITY_VARIANTS = {
  INFO: 'outlined',
  WARNING: 'outlined',
  HIGH: 'outlined',
  CRITICAL: 'filled',
};

const RECOMMENDED_ACTION_COLORS = {
  NO_ACTION: 'default',
  EXPEDITE: 'warning',
  DELAY_ACCEPTANCE: 'info',
  PARTIAL_RECEIPT: 'info',
  FIND_ALTERNATE: 'secondary',
  CANCEL_REORDER: 'error',
  QUALITY_INSPECTION: 'warning',
  PRICE_NEGOTIATION: 'info',
  ESCALATE: 'error',
};

const RECOMMENDED_ACTION_OPTIONS = [
  { value: 'NO_ACTION', label: 'No Action' },
  { value: 'EXPEDITE', label: 'Expedite' },
  { value: 'DELAY_ACCEPTANCE', label: 'Delay Acceptance' },
  { value: 'PARTIAL_RECEIPT', label: 'Partial Receipt' },
  { value: 'FIND_ALTERNATE', label: 'Find Alternate' },
  { value: 'CANCEL_REORDER', label: 'Cancel & Reorder' },
  { value: 'QUALITY_INSPECTION', label: 'Quality Inspection' },
  { value: 'PRICE_NEGOTIATION', label: 'Price Negotiation' },
  { value: 'ESCALATE', label: 'Escalate' },
];

const SEVERITY_OPTIONS = [
  { value: 'INFO', label: 'Info' },
  { value: 'WARNING', label: 'Warning' },
  { value: 'HIGH', label: 'High' },
  { value: 'CRITICAL', label: 'Critical' },
];

// ---------------------------------------------------------------------------
// Column definitions for TRMDecisionWorklist
// ---------------------------------------------------------------------------

const COLUMNS = [
  {
    key: 'order_id',
    label: 'Order ID',
    render: (decision) => (
      <Typography variant="body2" fontWeight="medium" sx={{ fontFamily: 'monospace' }}>
        {decision.order_id || '—'}
      </Typography>
    ),
  },
  {
    key: 'order_type',
    label: 'Order Type',
    render: (decision) => {
      const orderType = decision.order_type;
      if (!orderType) return '—';
      return (
        <Chip
          label={orderType}
          size="small"
          color={ORDER_TYPE_COLORS[orderType] || 'default'}
          variant="outlined"
        />
      );
    },
  },
  {
    key: 'exception_type',
    label: 'Exception Type',
    render: (decision) => {
      const exType = decision.exception_type;
      if (!exType) return '—';
      return (
        <Typography variant="body2">
          {exType.replace(/_/g, ' ')}
        </Typography>
      );
    },
  },
  {
    key: 'severity',
    label: 'Severity',
    render: (decision) => {
      const severity = decision.severity;
      if (!severity) return '—';
      return (
        <Chip
          label={severity}
          size="small"
          color={SEVERITY_COLORS[severity] || 'default'}
          variant={SEVERITY_VARIANTS[severity] || 'outlined'}
        />
      );
    },
  },
  {
    key: 'recommended_action',
    label: 'Recommended Action',
    render: (decision) => {
      const action = decision.recommended_action;
      if (!action) return '—';
      return (
        <Chip
          label={action.replace(/_/g, ' ')}
          size="small"
          color={RECOMMENDED_ACTION_COLORS[action] || 'default'}
          variant="outlined"
        />
      );
    },
  },
  {
    key: 'estimated_impact_cost',
    label: 'Impact ($)',
    render: (decision) => {
      const cost = decision.estimated_impact_cost;
      if (cost == null) return '—';
      return (
        <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
          ${Number(cost).toLocaleString(undefined, {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
          })}
        </Typography>
      );
    },
  },
  {
    key: 'partner_name',
    label: 'Partner',
    render: (decision) => decision.partner_name || '—',
  },
  {
    key: 'risk_bound',
    label: 'CDT Risk',
    render: (decision) => {
      if (decision.risk_bound == null) return '—';
      const pct = (decision.risk_bound * 100).toFixed(1);
      const color = decision.risk_bound < 0.1 ? 'success' : decision.risk_bound < 0.3 ? 'warning' : 'error';
      return (
        <MuiTooltip title={`P(loss > threshold) = ${pct}% from Conformal Decision Theory`} arrow>
          <Chip label={`${pct}%`} size="small" color={color} variant="outlined" />
        </MuiTooltip>
      );
    },
  },
];

// ---------------------------------------------------------------------------
// Override fields for the override dialog
// ---------------------------------------------------------------------------

const OVERRIDE_FIELDS = [
  {
    key: 'recommended_action',
    label: 'Recommended Action',
    type: 'text',
    options: RECOMMENDED_ACTION_OPTIONS,
    helperText: 'Select the action you believe should be taken for this exception',
  },
  {
    key: 'severity',
    label: 'Override Severity',
    type: 'text',
    options: SEVERITY_OPTIONS,
    helperText: 'Adjust the severity level if the AI assessment is incorrect',
  },
];

// ---------------------------------------------------------------------------
// Summary cards builder
// ---------------------------------------------------------------------------

const buildSummaryCards = (decisions) => {
  const proposed = decisions.filter((d) => d.status === 'INFORMED');
  const critical = decisions.filter((d) => d.severity === 'CRITICAL');

  // Average resolution time from completed decisions
  const completed = decisions.filter(
    (d) => d.status === 'COMPLETED' || d.status === 'OUTCOME_RECORDED'
  );
  let avgResolutionTime = '—';
  if (completed.length > 0) {
    const totalHours = completed.reduce((sum, d) => {
      if (d.resolution_time_hours != null) return sum + d.resolution_time_hours;
      if (d.timestamp && d.resolved_at) {
        const start = new Date(d.timestamp).getTime();
        const end = new Date(d.resolved_at).getTime();
        return sum + (end - start) / (1000 * 60 * 60);
      }
      return sum;
    }, 0);
    const avg = totalHours / completed.length;
    if (avg > 0) {
      avgResolutionTime = `${avg.toFixed(1)}h`;
    }
  }

  // Escalation rate
  const total = decisions.length;
  const escalated = decisions.filter(
    (d) =>
      d.recommended_action === 'ESCALATE' ||
      d.override_values?.recommended_action === 'ESCALATE'
  );
  const escalationRate =
    total > 0 ? `${((escalated.length / total) * 100).toFixed(0)}%` : '—';

  return [
    {
      title: 'Open Exceptions',
      value: proposed.length,
      color: proposed.length > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: 'Awaiting review',
    },
    {
      title: 'Critical',
      value: critical.length,
      color: critical.length > 0 ? '#d32f2f' : '#2e7d32',
      subtitle: 'Severity = CRITICAL',
    },
    {
      title: 'Avg Resolution Time',
      value: avgResolutionTime,
      color: '#1976d2',
      subtitle: 'From recent completed',
    },
    {
      title: 'Escalation Rate',
      value: escalationRate,
      color: '#9c27b0',
      subtitle: '% ESCALATE of total',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const OrderTrackingWorklistPage = ({ configId = 1 }) => {
  const location = useLocation();
  const initialStatusFilter = location.state?.filters?.status;
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_order_tracking_worklist');

  // Memoize the summary cards function so it has a stable reference
  const summaryCardsFn = useMemo(() => buildSummaryCards, []);

  if (capLoading) {
    return null;
  }

  if (!canManage) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">
          You do not have permission to manage the Order Tracking Worklist.
          Required capability: <strong>manage_order_tracking_worklist</strong>
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Order Tracking Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review order exceptions detected by the AI agent.
            Accept recommended actions, override with reasoning, or reject
            for re-evaluation. Overrides train the agent via reinforcement learning.
          </Typography>
        </Box>
        <LayerModeIndicator layer="order_tracking_trm" mode="active" />
      </Box>

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType="order_tracking"
        title="Order Tracking Worklist"
        columns={COLUMNS}
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

export default OrderTrackingWorklistPage;
