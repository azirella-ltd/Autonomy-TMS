/**
 * ATP Fulfillment Worklist Page
 *
 * Dedicated worklist for the ATP Analyst role — the human counterpart of the
 * ATP Executor TRM agent. The TRM proposes order fulfillment decisions
 * (FULFILL / PARTIAL / DEFER / REJECT) and the analyst reviews, accepts,
 * or overrides them before execution.
 *
 * Uses the shared TRMDecisionWorklist component with ATP-specific columns,
 * summary cards, and override fields.
 *
 * Adaptive Decision Hierarchy: Execution layer, VFA policy class.
 */
import React, { useState, useEffect } from 'react';
import { Box, Typography, Chip, Tooltip as MuiTooltip } from '@mui/material';

import TRMDecisionWorklist from '../../components/cascade/TRMDecisionWorklist';
import LayerModeIndicator from '../../components/cascade/LayerModeIndicator';
import { getTRMDecisions, submitTRMAction } from '../../services/planningCascadeApi';
import { useCapabilities } from '../../hooks/useCapabilities';
import { useAuth } from '../../contexts/AuthContext';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Color mapping for ATP recommended actions */
const ACTION_COLORS = {
  FULFILL: 'success',
  PARTIAL: 'warning',
  DEFER: 'info',
  REJECT: 'error',
};

/** Color mapping for customer priority tiers (1 = highest) */
const PRIORITY_COLORS = {
  1: '#d32f2f',   // red — critical / strategic
  2: '#f57c00',   // orange — high
  3: '#1976d2',   // blue — standard
  4: '#7b1fa2',   // purple — low
  5: '#757575',   // grey — transactional
};

const PRIORITY_LABELS = {
  1: 'P1 Critical',
  2: 'P2 High',
  3: 'P3 Standard',
  4: 'P4 Low',
  5: 'P5 Transactional',
};

// ---------------------------------------------------------------------------
// ATP-specific column definitions for TRMDecisionWorklist
// ---------------------------------------------------------------------------

const ATP_COLUMNS = [
  {
    key: 'product_id',
    label: 'Product',
    render: (decision) => (
      <Typography variant="body2" fontWeight="medium">
        {decision.sku || decision.product_id || '\u2014'}
      </Typography>
    ),
  },
  {
    key: 'customer_priority',
    label: 'Customer Priority',
    render: (decision) => {
      const priority = decision.customer_priority ?? decision.priority;
      if (priority == null) return <Chip label="\u2014" size="small" variant="outlined" />;
      const color = PRIORITY_COLORS[priority] || PRIORITY_COLORS[5];
      const label = PRIORITY_LABELS[priority] || `P${priority}`;
      return (
        <Chip
          label={label}
          size="small"
          sx={{
            bgcolor: color,
            color: '#fff',
            fontWeight: 600,
            fontSize: '0.7rem',
          }}
        />
      );
    },
  },
  {
    key: 'requested_qty',
    label: 'Requested Qty',
    render: (decision) => (
      <Typography variant="body2">
        {decision.requested_qty != null
          ? Number(decision.requested_qty).toLocaleString()
          : '\u2014'}
      </Typography>
    ),
  },
  {
    key: 'recommended_action',
    label: 'Recommended',
    render: (decision) => {
      const action = decision.recommended_action;
      if (!action) return <Chip label="\u2014" size="small" variant="outlined" />;
      return (
        <Chip
          label={action}
          size="small"
          color={ACTION_COLORS[action] || 'default'}
          variant="filled"
          sx={{ fontWeight: 600 }}
        />
      );
    },
  },
  {
    key: 'promised_qty',
    label: 'Promised Qty',
    render: (decision) => (
      <Typography variant="body2" fontWeight="medium">
        {decision.promised_qty != null
          ? Number(decision.promised_qty).toLocaleString()
          : '\u2014'}
      </Typography>
    ),
  },
  {
    key: 'risk_bound',
    label: 'CDT Risk',
    render: (decision) => {
      if (decision.risk_bound == null) return '\u2014';
      const pct = (decision.risk_bound * 100).toFixed(1);
      const color = decision.risk_bound < 0.1 ? 'success' : decision.risk_bound < 0.3 ? 'warning' : 'error';
      return (
        <MuiTooltip title={`P(loss > threshold) = ${pct}% from CDT`} arrow>
          <Chip label={`${pct}%`} size="small" color={color} variant="outlined" />
        </MuiTooltip>
      );
    },
  },
];

// ---------------------------------------------------------------------------
// Override fields for the override dialog
// ---------------------------------------------------------------------------

const ATP_OVERRIDE_FIELDS = [
  {
    key: 'promised_qty',
    label: 'Override Promised Qty',
    type: 'number',
    helperText: 'Enter the quantity you want to promise to this customer order.',
    inputProps: { min: 0 },
  },
  {
    key: 'recommended_action',
    label: 'Override Decision',
    type: 'text',
    options: [
      { value: 'FULFILL', label: 'FULFILL \u2014 Ship full requested quantity' },
      { value: 'PARTIAL', label: 'PARTIAL \u2014 Ship reduced quantity' },
      { value: 'DEFER', label: 'DEFER \u2014 Reschedule to later date' },
      { value: 'REJECT', label: 'REJECT \u2014 Cannot fulfill this order' },
    ],
    helperText: 'Select the fulfillment action to apply instead of the agent recommendation.',
  },
];

// ---------------------------------------------------------------------------
// Summary cards computation
// ---------------------------------------------------------------------------

/**
 * Compute summary card data from the decisions array.
 * Returns an array of { title, value, color, subtitle } objects consumed
 * by TRMDecisionWorklist's summaryCards prop.
 */
const computeSummaryCards = (decisions) => {
  if (!decisions || decisions.length === 0) {
    return [
      { title: 'Pending Decisions', value: '0', color: '#1976d2' },
      { title: 'Fill Rate', value: '\u2014', color: '#2e7d32' },
      { title: 'Avg Confidence', value: '\u2014', color: '#ed6c02' },
      { title: 'Override Rate', value: '\u2014', color: '#9c27b0' },
    ];
  }

  // Pending: count of PROPOSED status
  const pendingCount = decisions.filter((d) => d.status === 'PROPOSED').length;

  // Fill Rate: percentage of FULFILL decisions among those with a recommendation
  const withAction = decisions.filter((d) => d.recommended_action);
  const fulfillCount = withAction.filter((d) => d.recommended_action === 'FULFILL').length;
  const fillRate = withAction.length > 0
    ? ((fulfillCount / withAction.length) * 100).toFixed(1)
    : null;

  // Avg Confidence: mean of confidence values (excluding nulls)
  const confidences = decisions
    .map((d) => d.confidence)
    .filter((c) => c != null);
  const avgConfidence = confidences.length > 0
    ? ((confidences.reduce((sum, c) => sum + c, 0) / confidences.length) * 100).toFixed(1)
    : null;

  // Override Rate: percentage of OVERRIDDEN among total actioned (non-PROPOSED)
  const actioned = decisions.filter(
    (d) => d.status !== 'PROPOSED' && d.status !== 'REVIEWED'
  );
  const overriddenCount = actioned.filter((d) => d.status === 'OVERRIDDEN').length;
  const overrideRate = actioned.length > 0
    ? ((overriddenCount / actioned.length) * 100).toFixed(1)
    : null;

  return [
    {
      title: 'Pending Decisions',
      value: String(pendingCount),
      color: pendingCount > 0 ? '#ed6c02' : '#1976d2',
      subtitle: pendingCount > 0 ? 'Requires review' : 'All clear',
    },
    {
      title: 'Fill Rate',
      value: fillRate != null ? `${fillRate}%` : '\u2014',
      color: '#2e7d32',
      subtitle: `${fulfillCount} of ${withAction.length} orders fulfilled`,
    },
    {
      title: 'Avg Confidence',
      value: avgConfidence != null ? `${avgConfidence}%` : '\u2014',
      color: avgConfidence != null && parseFloat(avgConfidence) >= 90
        ? '#2e7d32'
        : avgConfidence != null && parseFloat(avgConfidence) >= 70
          ? '#ed6c02'
          : '#d32f2f',
      subtitle: `Across ${confidences.length} decisions`,
    },
    {
      title: 'Override Rate',
      value: overrideRate != null ? `${overrideRate}%` : '\u2014',
      color: '#9c27b0',
      subtitle: overrideRate != null
        ? `${overriddenCount} of ${actioned.length} overridden`
        : 'No actions yet',
    },
  ];
};

// ---------------------------------------------------------------------------
// ATPWorklistPage Component
// ---------------------------------------------------------------------------

const ATPWorklistPage = () => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const { user } = useAuth();

  // Resolve configId from user's organization (TRM decisions endpoint uses tenant_id)
  const [configId, setConfigId] = useState(user?.tenant_id || null);

  useEffect(() => {
    if (user?.tenant_id) setConfigId(user.tenant_id);
  }, [user?.tenant_id]);

  const canManage = !capLoading && hasCapability('manage_atp_worklist');

  return (
    <Box sx={{ p: 3 }}>
      {/* Page Header */}
      <Box
        display="flex"
        justifyContent="space-between"
        alignItems="flex-start"
        mb={3}
      >
        <Box>
          <Typography variant="h5" gutterBottom sx={{ fontWeight: 600 }}>
            ATP Fulfillment Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 700 }}>
            Review order fulfillment decisions proposed by the ATP Executor TRM agent.
            Each decision recommends whether to fulfill, partially fill, defer, or reject
            a customer order based on available inventory, priority allocation tiers,
            and service level targets.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType="atp"
        title="ATP Fulfillment Decisions"
        columns={ATP_COLUMNS}
        overrideFields={ATP_OVERRIDE_FIELDS}
        summaryCards={computeSummaryCards}
        fetchDecisions={getTRMDecisions}
        submitAction={submitTRMAction}
        canManage={canManage}
      />
    </Box>
  );
};

export default ATPWorklistPage;
