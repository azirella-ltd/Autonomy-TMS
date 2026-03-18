/**
 * Inventory Buffer Worklist Page
 *
 * Dedicated worklist for the Inventory Planner — human counterpart of the
 * Inventory Buffer TRM (formerly SafetyStockTRM). The TRM recommends buffer
 * parameter adjustments (multiplier changes, reoptimization) and the planner
 * reviews, accepts, overrides, or rejects each recommendation before execution.
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

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TRM_TYPE = 'inventory_buffer';
const DEFAULT_CONFIG_ID = 1;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a multiplier value with two decimal places and an 'x' suffix.
 */
const formatMultiplier = (value) => {
  if (value == null || isNaN(value)) return '—';
  return `${Number(value).toFixed(2)}x`;
};

/**
 * Format days of supply with one decimal.
 */
const formatDOS = (value) => {
  if (value == null || isNaN(value)) return '—';
  return `${Number(value).toFixed(1)} days`;
};

/**
 * Format a number with locale formatting.
 */
const formatNumber = (value) => {
  if (value == null || isNaN(value)) return '—';
  return Number(value).toLocaleString();
};

// ---------------------------------------------------------------------------
// Column definitions for TRMDecisionWorklist
// ---------------------------------------------------------------------------

const BUFFER_COLUMNS = [
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
    key: 'location_id',
    label: 'Location',
    render: (d) => d.location_id || '—',
  },
  {
    key: 'baseline_ss',
    label: 'Baseline',
    render: (d) => formatNumber(d.baseline_ss),
  },
  {
    key: 'adjusted_ss',
    label: 'Adjusted',
    render: (d) => {
      if (d.adjusted_ss == null) return '—';
      const baseline = Number(d.baseline_ss) || 0;
      const adjusted = Number(d.adjusted_ss);
      const color = adjusted > baseline ? '#ed6c02' : adjusted < baseline ? '#1565c0' : undefined;
      return (
        <Typography variant="body2" sx={{ color, fontWeight: 'medium' }}>
          {formatNumber(d.adjusted_ss)}
        </Typography>
      );
    },
  },
  {
    key: 'multiplier',
    label: 'Multiplier',
    render: (d) => {
      if (d.multiplier == null) return '—';
      const mult = Number(d.multiplier);
      const color = mult > 1.0 ? 'warning' : mult < 1.0 ? 'info' : 'default';
      return (
        <Chip
          label={formatMultiplier(d.multiplier)}
          size="small"
          color={color}
          variant="outlined"
        />
      );
    },
  },
  {
    key: 'current_dos',
    label: 'DOS',
    render: (d) => formatDOS(d.current_dos),
  },
  {
    key: 'reason',
    label: 'Trigger',
    render: (d) => d.reason || '—',
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

const BUFFER_OVERRIDE_FIELDS = [
  {
    key: 'adjusted_ss',
    label: 'Override Buffer Level',
    type: 'number',
    helperText: 'Enter a new buffer level to replace the AI recommendation',
  },
  {
    key: 'multiplier',
    label: 'Override Multiplier',
    type: 'number',
    helperText: 'Enter a new multiplier (e.g. 1.25 for 25% increase)',
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

  // Average multiplier across all decisions
  const multipliers = decisions
    .filter((d) => d.multiplier != null && !isNaN(d.multiplier))
    .map((d) => Number(d.multiplier));
  const avgMultiplier =
    multipliers.length > 0
      ? (multipliers.reduce((sum, m) => sum + m, 0) / multipliers.length).toFixed(2)
      : '1.00';

  // Increases vs decreases
  const increaseCount = decisions.filter(
    (d) => d.multiplier != null && Number(d.multiplier) > 1.0
  ).length;
  const decreaseCount = decisions.filter(
    (d) => d.multiplier != null && Number(d.multiplier) < 1.0
  ).length;

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
      title: 'Pending Adjustments',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'Avg Multiplier',
      value: `${avgMultiplier}x`,
      color: Number(avgMultiplier) > 1.2 ? '#ed6c02' : '#1565c0',
      subtitle: `Across ${multipliers.length} adjustments`,
    },
    {
      title: 'Increases vs Decreases',
      value: `${increaseCount} / ${decreaseCount}`,
      color: '#1565c0',
      subtitle: `${increaseCount} up, ${decreaseCount} down`,
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

const BufferWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const location = useLocation();
  const initialStatusFilter = location.state?.filters?.status;
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_buffer_worklist');
  const { formatProduct, formatSite, loadLookupsForConfig } = useDisplayPreferences();

  useEffect(() => { loadLookupsForConfig(configId); }, [configId, loadLookupsForConfig]);

  // Memoize columns with display preference resolvers
  const columns = useMemo(() => BUFFER_COLUMNS.map((col) => {
    if (col.key === 'product_id') {
      return { ...col, render: (d) => (
        <Typography variant="body2" fontWeight="medium">
          {formatProduct(d.product_id, d.product_name) || '\u2014'}
        </Typography>
      )};
    }
    if (col.key === 'location_id') {
      return { ...col, render: (d) => formatSite(d.location_id, d.location_name) || '\u2014' };
    }
    return col;
  }), [formatProduct, formatSite]);

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
            Inventory Buffer Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review inventory buffer adjustment recommendations from the
            AI agent. Accept, override with reason, or reject
            each decision before execution.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Tenant Admin
          to request the <strong>manage_buffer_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Inventory Buffer Worklist"
        columns={columns}
        overrideFields={BUFFER_OVERRIDE_FIELDS}
        summaryCards={summaryCardsFn}
        fetchDecisions={getTRMDecisions}
        submitAction={submitTRMAction}
        canManage={canManage}
        initialStatusFilter={initialStatusFilter}
      />
    </Box>
  );
};

export default BufferWorklistPage;
