/**
 * Subcontracting Worklist Page
 *
 * Dedicated worklist for the Procurement Planner — human counterpart of the
 * Subcontracting TRM. The TRM recommends make-vs-buy routing decisions
 * (INTERNAL / EXTERNAL / SPLIT) and the planner reviews, accepts,
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

const TRM_TYPE = 'subcontracting';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for routing decision chips */
const ROUTING_COLORS = {
  internal: 'success',
  external: 'warning',
  split: 'info',
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

const SUBCONTRACTING_COLUMNS = [
  {
    key: 'product_id',
    label: 'Product',
    render: (d) => (
      <Typography variant="body2" fontWeight="medium">
        {d.product_id || '—'}
      </Typography>
    ),
  },
  {
    key: 'site_id',
    label: 'Site',
    render: (d) => d.site_id || '—',
  },
  {
    key: 'routing_decision',
    label: 'Routing',
    render: (d) => {
      const routing = d.routing_decision || '—';
      return (
        <Chip
          label={routing}
          size="small"
          color={ROUTING_COLORS[routing] || 'default'}
          variant="filled"
        />
      );
    },
  },
  {
    key: 'required_qty',
    label: 'Qty',
    render: (d) =>
      d.required_qty != null
        ? Number(d.required_qty).toLocaleString()
        : '—',
  },
  {
    key: 'internal_cost_per_unit',
    label: 'Int. Cost',
    render: (d) => formatCurrency(d.internal_cost_per_unit),
  },
  {
    key: 'subcontractor_cost_per_unit',
    label: 'Ext. Cost',
    render: (d) => formatCurrency(d.subcontractor_cost_per_unit),
  },
  {
    key: 'subcontractor_id',
    label: 'Subcontractor',
    render: (d) => d.subcontractor_id || '—',
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

const SUBCONTRACTING_OVERRIDE_FIELDS = [
  {
    key: 'routing_decision',
    label: 'Override Routing',
    type: 'text',
    options: [
      { value: 'internal', label: 'Internal' },
      { value: 'external', label: 'External' },
      { value: 'split', label: 'Split' },
    ],
    helperText: 'Change the recommended routing (internal, external, split)',
  },
  {
    key: 'required_qty',
    label: 'Override Qty',
    type: 'number',
    helperText: 'Enter a new required quantity to replace the agent recommendation',
  },
  {
    key: 'subcontractor_id',
    label: 'Override Subcontractor',
    type: 'text',
    helperText: 'Enter an alternative subcontractor ID',
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

  // External rate: fraction of all decisions routed externally
  const externalCount = decisions.filter(
    (d) => d.routing_decision === 'external'
  ).length;
  const externalRate =
    decisions.length > 0
      ? ((externalCount / decisions.length) * 100).toFixed(1)
      : '0.0';

  // Average cost delta (external - internal)
  const costDeltas = decisions
    .filter(
      (d) =>
        d.internal_cost_per_unit != null &&
        d.subcontractor_cost_per_unit != null &&
        !isNaN(d.internal_cost_per_unit) &&
        !isNaN(d.subcontractor_cost_per_unit)
    )
    .map(
      (d) =>
        Number(d.subcontractor_cost_per_unit) -
        Number(d.internal_cost_per_unit)
    );
  const avgCostDelta =
    costDeltas.length > 0
      ? costDeltas.reduce((sum, d) => sum + d, 0) / costDeltas.length
      : 0;

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
      title: 'Pending Decisions',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'External %',
      value: `${externalRate}%`,
      color: Number(externalRate) > 40 ? '#ed6c02' : '#1565c0',
      subtitle: `${externalCount} of ${decisions.length} decisions`,
    },
    {
      title: 'Avg Cost Delta',
      value: formatCurrency(avgCostDelta),
      color: avgCostDelta > 0 ? '#d32f2f' : '#2e7d32',
      subtitle: 'External vs internal per unit',
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

const SubcontractingWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_subcontracting_worklist');

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
            Subcontracting Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review make-vs-buy routing recommendations from the subcontracting agent.
            Accept, override with reason, or reject each decision before
            execution.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Tenant Admin
          to request the <strong>manage_subcontracting_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Subcontracting Worklist"
        columns={SUBCONTRACTING_COLUMNS}
        overrideFields={SUBCONTRACTING_OVERRIDE_FIELDS}
        summaryCards={summaryCardsFn}
        fetchDecisions={getTRMDecisions}
        submitAction={submitTRMAction}
        canManage={canManage}
      />
    </Box>
  );
};

export default SubcontractingWorklistPage;
