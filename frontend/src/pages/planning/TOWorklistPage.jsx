/**
 * TO Execution Worklist Page
 *
 * Dedicated worklist for the Logistics Planner — human counterpart of the
 * TO Execution TRM. The TRM recommends transfer order execution decisions
 * (RELEASE / EXPEDITE / DEFER / CONSOLIDATE) and the planner reviews, accepts,
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

const TRM_TYPE = 'to_execution';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for decision type chips */
const DECISION_COLORS = {
  release: 'success',
  expedite: 'warning',
  defer: 'default',
  consolidate: 'info',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format confidence as a percentage.
 */
const formatConfidence = (value) => {
  if (value == null || isNaN(value)) return '—';
  return `${(Number(value) * 100).toFixed(1)}%`;
};

// ---------------------------------------------------------------------------
// Column definitions for TRMDecisionWorklist
// ---------------------------------------------------------------------------

const TO_COLUMNS = [
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
    key: 'source_site_id',
    label: 'From',
    render: (d) => d.source_site_id || '—',
  },
  {
    key: 'dest_site_id',
    label: 'To',
    render: (d) => d.dest_site_id || '—',
  },
  {
    key: 'transfer_order_id',
    label: 'TO #',
    render: (d) => d.transfer_order_id || '—',
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
    key: 'planned_qty',
    label: 'Qty',
    render: (d) =>
      d.planned_qty != null
        ? Number(d.planned_qty).toLocaleString()
        : '—',
  },
  {
    key: 'transportation_mode',
    label: 'Mode',
    render: (d) => d.transportation_mode || '—',
  },
  {
    key: 'confidence',
    label: 'Confidence',
    render: (d) => {
      if (d.confidence == null) return '—';
      const pct = (d.confidence * 100).toFixed(1);
      const color = d.confidence >= 0.8 ? 'success' : d.confidence >= 0.5 ? 'warning' : 'error';
      return (
        <MuiTooltip title={`Likelihood: ${pct}%`} arrow>
          <Chip label={`${pct}%`} size="small" color={color} variant="outlined" />
        </MuiTooltip>
      );
    },
  },
];

// ---------------------------------------------------------------------------
// Override field definitions for the Override Dialog
// ---------------------------------------------------------------------------

const TO_OVERRIDE_FIELDS = [
  {
    key: 'decision_type',
    label: 'Override Decision',
    type: 'text',
    options: [
      { value: 'release', label: 'Release' },
      { value: 'expedite', label: 'Expedite' },
      { value: 'defer', label: 'Defer' },
      { value: 'consolidate', label: 'Consolidate' },
    ],
    helperText: 'Change the recommended decision (release, expedite, defer, consolidate)',
  },
  {
    key: 'planned_qty',
    label: 'Override Qty',
    type: 'number',
    helperText: 'Enter a new transfer quantity to replace the AI recommendation',
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

  // Total units across proposed TOs
  const totalUnits = proposed.reduce(
    (sum, d) => sum + (Number(d.planned_qty) || 0),
    0
  );

  // Expedite rate: fraction of all decisions that are expedite
  const expediteCount = decisions.filter(
    (d) => d.decision_type === 'expedite'
  ).length;
  const expediteRate =
    decisions.length > 0
      ? ((expediteCount / decisions.length) * 100).toFixed(1)
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
      title: 'Pending TOs',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'Total Units',
      value: totalUnits.toLocaleString(),
      color: '#1565c0',
      subtitle: 'Proposed transfer quantity',
    },
    {
      title: 'Expedite Rate',
      value: `${expediteRate}%`,
      color: Number(expediteRate) > 15 ? '#d32f2f' : '#2e7d32',
      subtitle: `${expediteCount} of ${decisions.length} decisions`,
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

const TOWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_to_worklist');

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
            TO Execution Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review transfer order recommendations from the AI agent.
            Accept, override with reason, or reject each decision before
            execution.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Tenant Admin
          to request the <strong>manage_to_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="TO Execution Worklist"
        columns={TO_COLUMNS}
        overrideFields={TO_OVERRIDE_FIELDS}
        summaryCards={summaryCardsFn}
        fetchDecisions={getTRMDecisions}
        submitAction={submitTRMAction}
        canManage={canManage}
      />
    </Box>
  );
};

export default TOWorklistPage;
