/**
 * Quality Disposition Worklist Page
 *
 * Dedicated worklist for the Quality Engineer — human counterpart of the
 * Quality Disposition TRM. The TRM recommends quality disposition decisions
 * (ACCEPT / REJECT / REWORK / SCRAP / USE_AS_IS) and the engineer reviews,
 * accepts, overrides, or rejects each recommendation before execution.
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

const TRM_TYPE = 'quality_disposition';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for disposition chips */
const DISPOSITION_COLORS = {
  accept: 'success',
  reject: 'error',
  rework: 'warning',
  scrap: 'error',
  use_as_is: 'info',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a value as a percentage.
 */
const formatPercent = (value) => {
  if (value == null || isNaN(value)) return '—';
  return `${(Number(value) * 100).toFixed(1)}%`;
};

// ---------------------------------------------------------------------------
// Column definitions for TRMDecisionWorklist
// ---------------------------------------------------------------------------

const QUALITY_COLUMNS = [
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
    key: 'quality_order_id',
    label: 'QO #',
    render: (d) => d.quality_order_id || '—',
  },
  {
    key: 'lot_number',
    label: 'Lot',
    render: (d) => d.lot_number || '—',
  },
  {
    key: 'disposition',
    label: 'Disposition',
    render: (d) => {
      const disposition = d.disposition || '—';
      return (
        <Chip
          label={disposition}
          size="small"
          color={DISPOSITION_COLORS[disposition] || 'default'}
          variant="filled"
        />
      );
    },
  },
  {
    key: 'inspection_type',
    label: 'Inspection',
    render: (d) => d.inspection_type || '—',
  },
  {
    key: 'defect_rate',
    label: 'Defect Rate',
    render: (d) => formatPercent(d.defect_rate),
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

const QUALITY_OVERRIDE_FIELDS = [
  {
    key: 'disposition',
    label: 'Override Disposition',
    type: 'text',
    options: [
      { value: 'accept', label: 'Accept' },
      { value: 'reject', label: 'Reject' },
      { value: 'rework', label: 'Rework' },
      { value: 'scrap', label: 'Scrap' },
      { value: 'use_as_is', label: 'Use As-Is' },
    ],
    helperText: 'Change the recommended disposition (accept, reject, rework, scrap, use_as_is)',
  },
  {
    key: 'disposition_reason',
    label: 'Disposition Reason',
    type: 'text',
    helperText: 'Provide a reason for the disposition override',
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

  // Average defect rate across all decisions
  const defectRates = decisions
    .filter((d) => d.defect_rate != null && !isNaN(d.defect_rate))
    .map((d) => Number(d.defect_rate));
  const avgDefectRate =
    defectRates.length > 0
      ? ((defectRates.reduce((sum, r) => sum + r, 0) / defectRates.length) * 100).toFixed(1)
      : '0.0';

  // Accept rate: fraction of all decisions with accept disposition
  const acceptCount = decisions.filter(
    (d) => d.disposition === 'accept'
  ).length;
  const acceptRate =
    decisions.length > 0
      ? ((acceptCount / decisions.length) * 100).toFixed(1)
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
      title: 'Pending QOs',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'Avg Defect Rate',
      value: `${avgDefectRate}%`,
      color: Number(avgDefectRate) > 5 ? '#d32f2f' : '#2e7d32',
      subtitle: `Across ${defectRates.length} inspections`,
    },
    {
      title: 'Accept Rate',
      value: `${acceptRate}%`,
      color: Number(acceptRate) >= 80 ? '#2e7d32' : '#ed6c02',
      subtitle: `${acceptCount} of ${decisions.length} decisions`,
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

const QualityWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_quality_worklist');

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
            Quality Disposition Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review quality disposition recommendations from the AI agent.
            Accept, override with reason, or reject each decision before
            execution.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Tenant Admin
          to request the <strong>manage_quality_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Quality Disposition Worklist"
        columns={QUALITY_COLUMNS}
        overrideFields={QUALITY_OVERRIDE_FIELDS}
        summaryCards={summaryCardsFn}
        fetchDecisions={getTRMDecisions}
        submitAction={submitTRMAction}
        canManage={canManage}
      />
    </Box>
  );
};

export default QualityWorklistPage;
