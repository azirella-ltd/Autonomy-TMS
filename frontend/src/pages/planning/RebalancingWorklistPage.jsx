/**
 * Rebalancing Worklist Page
 *
 * Dedicated worklist for the Rebalancing Analyst — the human counterpart
 * of the Inventory Rebalancing TRM. The TRM proposes cross-location
 * inventory transfers (TRANSFER / HOLD / EXPEDITE) to optimize days-of-supply
 * across the network. The analyst reviews, accepts, overrides, or rejects
 * each recommendation before execution.
 *
 * Uses the shared TRMDecisionWorklist component with rebalancing-specific
 * columns, summary cards, and override fields.
 */
import React from 'react';
import {
  Box,
  Typography,
  Chip,
  LinearProgress,
  Alert,
} from '@mui/material';

import TRMDecisionWorklist from '../../components/cascade/TRMDecisionWorklist';
import LayerModeIndicator from '../../components/cascade/LayerModeIndicator';
import { getTRMDecisions, submitTRMAction } from '../../services/planningCascadeApi';
import { useCapabilities } from '../../hooks/useCapabilities';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TRM_TYPE = 'rebalancing';
const DEFAULT_CONFIG_ID = 1;

/**
 * Color mapping for recommended action chips.
 */
const ACTION_COLORS = {
  TRANSFER: 'primary',
  HOLD: 'default',
  EXPEDITE: 'warning',
};

/**
 * Color mapping for trigger reason chips.
 */
const REASON_COLORS = {
  STOCKOUT_RISK: 'error',
  EXCESS_INVENTORY: 'info',
  DEMAND_SPIKE: 'warning',
  SEASONAL_BUILDUP: 'secondary',
  REBALANCE_NETWORK: 'default',
  SERVICE_LEVEL: 'warning',
  EXPIRY_RISK: 'error',
};

// ---------------------------------------------------------------------------
// Column definitions for the TRMDecisionWorklist
// ---------------------------------------------------------------------------

const REBALANCING_COLUMNS = [
  {
    key: 'product_id',
    label: 'Product',
    render: (decision) => (
      <Typography variant="body2" fontWeight="medium">
        {decision.product_id || '—'}
      </Typography>
    ),
  },
  {
    key: 'from_site',
    label: 'From Site',
    render: (decision) => (
      <Typography variant="body2">
        {decision.from_site || '—'}
      </Typography>
    ),
  },
  {
    key: 'to_site',
    label: 'To Site',
    render: (decision) => (
      <Typography variant="body2">
        {decision.to_site || '—'}
      </Typography>
    ),
  },
  {
    key: 'recommended_action',
    label: 'Recommended',
    render: (decision) => {
      const action = decision.recommended_action;
      if (!action) return '—';
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
  {
    key: 'quantity',
    label: 'Transfer Qty',
    render: (decision) => (
      <Typography variant="body2" fontWeight="medium">
        {decision.quantity != null ? decision.quantity.toLocaleString() : '—'}
      </Typography>
    ),
  },
  {
    key: 'trigger_reason',
    label: 'Reason',
    render: (decision) => {
      const reason = decision.trigger_reason;
      if (!reason) return '—';
      return (
        <Chip
          label={reason.replace(/_/g, ' ')}
          size="small"
          color={REASON_COLORS[reason] || 'default'}
          variant="outlined"
        />
      );
    },
  },
  {
    key: 'urgency',
    label: 'Urgency',
    render: (decision) => {
      const urgency = decision.urgency;
      if (urgency == null) return '—';
      const pct = Math.round(urgency * 100);
      const color =
        urgency >= 0.8 ? 'error' : urgency >= 0.5 ? 'warning' : 'primary';
      return (
        <Box display="flex" alignItems="center" gap={1} minWidth={100}>
          <LinearProgress
            variant="determinate"
            value={pct}
            color={color}
            sx={{ flexGrow: 1, height: 8, borderRadius: 4 }}
          />
          <Typography variant="caption" sx={{ minWidth: 32, textAlign: 'right' }}>
            {pct}%
          </Typography>
        </Box>
      );
    },
  },
];

// ---------------------------------------------------------------------------
// Override fields for the Override Dialog
// ---------------------------------------------------------------------------

const OVERRIDE_FIELDS = [
  {
    key: 'quantity',
    label: 'Override Transfer Qty',
    type: 'number',
    helperText: 'Adjust the transfer quantity recommended by the TRM',
    inputProps: { min: 0 },
  },
  {
    key: 'to_site',
    label: 'Override Destination Site',
    type: 'text',
    helperText: 'Redirect the transfer to a different destination site',
  },
  {
    key: 'recommended_action',
    label: 'Override Action',
    type: 'text',
    options: [
      { value: 'TRANSFER', label: 'TRANSFER — Move inventory between sites' },
      { value: 'HOLD', label: 'HOLD — Keep inventory at current site' },
      { value: 'EXPEDITE', label: 'EXPEDITE — Urgent transfer with expedited shipping' },
    ],
    helperText: 'Change the recommended action type',
  },
];

// ---------------------------------------------------------------------------
// Summary cards builder
// ---------------------------------------------------------------------------

/**
 * Compute summary card data from the current set of decisions.
 *
 * Cards:
 * 1. Pending Transfers — count of PROPOSED decisions
 * 2. DOS Improvement — average DOS improvement across recent completed transfers
 * 3. Transfer Cost — sum of expected_cost for recent decisions
 * 4. Override Rate — percentage of OVERRIDDEN vs (ACCEPTED + OVERRIDDEN)
 */
const buildSummaryCards = (decisions) => {
  const proposed = decisions.filter((d) => d.status === 'PROPOSED');
  const pendingCount = proposed.length;

  // DOS improvement: average of dos_improvement field on completed decisions
  const withDos = decisions.filter(
    (d) => d.dos_improvement != null && d.status !== 'PROPOSED'
  );
  const avgDos =
    withDos.length > 0
      ? (withDos.reduce((sum, d) => sum + d.dos_improvement, 0) / withDos.length).toFixed(1)
      : '—';

  // Transfer cost: sum of expected_cost on recent decisions
  const recentWithCost = decisions.filter((d) => d.expected_cost != null);
  const totalCost = recentWithCost.reduce((sum, d) => sum + d.expected_cost, 0);
  const formattedCost =
    recentWithCost.length > 0
      ? `$${totalCost.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
      : '—';

  // Override rate
  const accepted = decisions.filter((d) => d.status === 'ACCEPTED').length;
  const overridden = decisions.filter((d) => d.status === 'OVERRIDDEN').length;
  const reviewedTotal = accepted + overridden;
  const overrideRate =
    reviewedTotal > 0
      ? `${((overridden / reviewedTotal) * 100).toFixed(0)}%`
      : '—';
  const overrideColor =
    reviewedTotal === 0
      ? '#1976d2'
      : overridden / reviewedTotal > 0.3
        ? '#d32f2f'
        : overridden / reviewedTotal > 0.15
          ? '#ed6c02'
          : '#2e7d32';

  return [
    {
      title: 'Pending Transfers',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: pendingCount === 1 ? '1 decision awaiting review' : `${pendingCount} decisions awaiting review`,
    },
    {
      title: 'DOS Improvement',
      value: avgDos !== '—' ? `${avgDos} days` : avgDos,
      color: '#1976d2',
      subtitle: withDos.length > 0 ? `Avg across ${withDos.length} transfers` : 'No completed transfers yet',
    },
    {
      title: 'Transfer Cost',
      value: formattedCost,
      color: '#7b1fa2',
      subtitle: recentWithCost.length > 0 ? `${recentWithCost.length} transfers with cost data` : 'No cost data available',
    },
    {
      title: 'Override Rate',
      value: overrideRate,
      color: overrideColor,
      subtitle: reviewedTotal > 0 ? `${overridden} of ${reviewedTotal} reviewed` : 'No reviewed decisions yet',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const RebalancingWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_rebalancing_worklist');

  if (capLoading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" p={6}>
        <Typography variant="body2" color="text.secondary">
          Loading permissions...
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Inventory Rebalancing Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review cross-location transfer recommendations from the Inventory
            Rebalancing TRM. Accept, override, or reject each decision before
            execution. Override reasons are captured for RL training.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to the rebalancing worklist. Contact your
          Group Admin to request the <strong>manage_rebalancing_worklist</strong>{' '}
          capability for Accept / Override / Reject actions.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Inventory Rebalancing Worklist"
        columns={REBALANCING_COLUMNS}
        overrideFields={OVERRIDE_FIELDS}
        summaryCards={buildSummaryCards}
        fetchDecisions={getTRMDecisions}
        submitAction={submitTRMAction}
        canManage={canManage}
      />
    </Box>
  );
};

export default RebalancingWorklistPage;
