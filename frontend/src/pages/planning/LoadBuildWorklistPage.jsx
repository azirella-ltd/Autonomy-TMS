/**
 * Load Build Worklist Page
 *
 * Dedicated worklist for the Load Planner — human counterpart of the
 * Load Build TRM. The TRM recommends load consolidation and optimization
 * decisions (CONSOLIDATE / SPLIT / HOLD / EXPEDITE) and the planner reviews,
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

const TRM_TYPE = 'load_build';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for recommended action chips */
const ACTION_COLORS = {
  CONSOLIDATE: 'success',
  SPLIT: 'info',
  HOLD: 'default',
  EXPEDITE: 'warning',
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
 * Format a percentage value with one decimal.
 */
const formatPercent = (value) => {
  if (value == null || isNaN(value)) return '—';
  return `${Number(value).toFixed(1)}%`;
};

// ---------------------------------------------------------------------------
// Column definitions for TRMDecisionWorklist
// ---------------------------------------------------------------------------

const COLUMNS = [
  {
    key: 'shipment_count',
    label: 'Shipments',
    render: (d) => (
      <Typography variant="body2" fontWeight="medium">
        {d.shipment_count != null ? Number(d.shipment_count).toLocaleString() : '—'}
      </Typography>
    ),
  },
  {
    key: 'lane_id',
    label: 'Lane',
    render: (d) => d.lane_id || '—',
  },
  {
    key: 'equipment_type',
    label: 'Equipment',
    render: (d) => {
      const type = d.equipment_type || '—';
      return <Chip label={type} size="small" variant="outlined" />;
    },
  },
  {
    key: 'weight_utilization',
    label: 'Weight Util %',
    render: (d) => {
      if (d.total_weight == null || d.max_weight == null || d.max_weight === 0) return '—';
      const pct = (Number(d.total_weight) / Number(d.max_weight)) * 100;
      const color = pct > 95 ? '#d32f2f' : pct > 80 ? '#2e7d32' : '#ed6c02';
      return (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box sx={{ flex: 1, bgcolor: '#e0e0e0', borderRadius: 1, height: 8, minWidth: 60 }}>
            <Box sx={{ width: `${Math.min(pct, 100)}%`, bgcolor: color, borderRadius: 1, height: 8 }} />
          </Box>
          <Typography variant="caption" sx={{ color }}>{formatPercent(pct)}</Typography>
        </Box>
      );
    },
  },
  {
    key: 'volume_utilization',
    label: 'Volume Util %',
    render: (d) => {
      if (d.total_volume == null || d.max_volume == null || d.max_volume === 0) return '—';
      const pct = (Number(d.total_volume) / Number(d.max_volume)) * 100;
      const color = pct > 95 ? '#d32f2f' : pct > 80 ? '#2e7d32' : '#ed6c02';
      return (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box sx={{ flex: 1, bgcolor: '#e0e0e0', borderRadius: 1, height: 8, minWidth: 60 }}>
            <Box sx={{ width: `${Math.min(pct, 100)}%`, bgcolor: color, borderRadius: 1, height: 8 }} />
          </Box>
          <Typography variant="caption" sx={{ color }}>{formatPercent(pct)}</Typography>
        </Box>
      );
    },
  },
  {
    key: 'consolidation_savings',
    label: 'Savings',
    render: (d) => formatCurrency(d.consolidation_savings),
  },
  {
    key: 'conflicts',
    label: 'Conflicts',
    render: (d) => {
      const hasConflict = d.has_hazmat_conflict || d.has_temp_conflict;
      return (
        <Chip
          label={hasConflict ? 'Yes' : 'No'}
          size="small"
          color={hasConflict ? 'error' : 'default'}
          variant={hasConflict ? 'filled' : 'outlined'}
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
    key: 'action',
    label: 'Override Action',
    type: 'text',
    options: [
      { value: 'consolidate', label: 'Consolidate' },
      { value: 'split', label: 'Split' },
      { value: 'hold', label: 'Hold' },
      { value: 'expedite', label: 'Expedite' },
    ],
    helperText: 'Change the recommended action',
  },
  {
    key: 'equipment_type',
    label: 'Equipment Type',
    type: 'text',
    options: [
      { value: 'dry_van', label: 'Dry Van' },
      { value: 'reefer', label: 'Reefer' },
      { value: 'flatbed', label: 'Flatbed' },
      { value: 'container', label: 'Container' },
    ],
    helperText: 'Override equipment type',
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

  // Avg utilization (weight-based)
  const utilizations = decisions
    .map((d) => {
      if (d.total_weight == null || d.max_weight == null || d.max_weight === 0) return NaN;
      return (Number(d.total_weight) / Number(d.max_weight)) * 100;
    })
    .filter((v) => !isNaN(v));
  const avgUtil =
    utilizations.length > 0
      ? (utilizations.reduce((s, v) => s + v, 0) / utilizations.length).toFixed(1)
      : '0.0';

  // Total savings
  const totalSavings = decisions.reduce(
    (sum, d) => sum + (Number(d.consolidation_savings) || 0),
    0
  );

  // Conflict count
  const conflictCount = decisions.filter(
    (d) => d.has_hazmat_conflict || d.has_temp_conflict
  ).length;

  return [
    {
      title: 'Pending Builds',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'Avg Utilization %',
      value: `${avgUtil}%`,
      color: Number(avgUtil) < 70 ? '#d32f2f' : '#2e7d32',
      subtitle: 'Average weight utilization',
    },
    {
      title: 'Total Savings',
      value: formatCurrency(totalSavings),
      color: '#1565c0',
      subtitle: 'Consolidation savings',
    },
    {
      title: 'Conflict Count',
      value: conflictCount,
      color: conflictCount > 0 ? '#d32f2f' : '#2e7d32',
      subtitle: `${conflictCount} loads with conflicts`,
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const LoadBuildWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const location = useLocation();
  const initialStatusFilter = location.state?.filters?.status;
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_load_build_worklist');
  const { formatSite, loadLookupsForConfig } = useDisplayPreferences();

  useEffect(() => { loadLookupsForConfig(configId); }, [configId, loadLookupsForConfig]);

  // Memoize columns with display preference resolvers
  const columns = useMemo(() => COLUMNS.map((col) => {
    if (col.key === 'lane_id') {
      return { ...col, render: (d) => formatSite(d.lane_id, d.lane_name) || '—' };
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
      <RoleTimeSeries roleKey="load_build" compact className="mb-4" />
      {/* Header */}
      <Box
        display="flex"
        justifyContent="space-between"
        alignItems="center"
        mb={3}
      >
        <Box>
          <Typography variant="h5" gutterBottom>
            Load Build Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review load consolidation and optimization recommendations from the AI agent.
            Accept, override with reason, or reject each decision before
            execution.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_load_build_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Load Build Worklist"
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

export default LoadBuildWorklistPage;
