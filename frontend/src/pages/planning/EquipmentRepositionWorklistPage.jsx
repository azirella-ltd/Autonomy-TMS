/**
 * Equipment Reposition Worklist Page
 *
 * Dedicated worklist for the Equipment Manager — human counterpart of the
 * Equipment Reposition TRM. The TRM recommends empty container and trailer
 * repositioning decisions (REPOSITION / HOLD / DEFER) and the manager reviews,
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

const TRM_TYPE = 'equipment_reposition';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for recommended action chips */
const ACTION_COLORS = {
  REPOSITION: 'success',
  HOLD: 'default',
  DEFER: 'info',
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
    key: 'equipment_type',
    label: 'Equipment',
    render: (d) => {
      const type = d.equipment_type || '—';
      return <Chip label={type} size="small" variant="outlined" />;
    },
  },
  {
    key: 'source_facility_id',
    label: 'Source',
    render: (d) => (
      <Typography variant="body2" fontWeight="medium">
        {d.source_facility_id || '—'}
      </Typography>
    ),
  },
  {
    key: 'source_surplus',
    label: 'Surplus',
    render: (d) =>
      d.source_surplus != null
        ? Number(d.source_surplus).toLocaleString()
        : '—',
  },
  {
    key: 'target_facility_id',
    label: 'Target',
    render: (d) => (
      <Typography variant="body2" fontWeight="medium">
        {d.target_facility_id || '—'}
      </Typography>
    ),
  },
  {
    key: 'target_deficit',
    label: 'Deficit',
    render: (d) =>
      d.target_deficit != null
        ? Number(d.target_deficit).toLocaleString()
        : '—',
  },
  {
    key: 'reposition_miles',
    label: 'Miles',
    render: (d) =>
      d.reposition_miles != null
        ? Number(d.reposition_miles).toLocaleString()
        : '—',
  },
  {
    key: 'reposition_cost',
    label: 'Cost',
    render: (d) => formatCurrency(d.reposition_cost),
  },
  {
    key: 'reposition_roi',
    label: 'ROI',
    render: (d) => {
      if (d.reposition_roi == null) return '—';
      const val = Number(d.reposition_roi);
      const color = val > 1.5 ? '#2e7d32' : val > 1.0 ? '#ed6c02' : '#d32f2f';
      return (
        <Typography variant="body2" sx={{ color, fontWeight: val > 1.5 ? 'bold' : 'normal' }}>
          {val.toFixed(2)}x
        </Typography>
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
    key: 'quantity',
    label: 'Equipment Quantity',
    type: 'number',
    helperText: 'Override equipment quantity',
  },
  {
    key: 'target_facility',
    label: 'Target Facility',
    type: 'text',
    helperText: 'Specify alternative target facility',
  },
  {
    key: 'action',
    label: 'Override Action',
    type: 'text',
    options: [
      { value: 'reposition', label: 'Reposition' },
      { value: 'hold', label: 'Hold' },
      { value: 'defer', label: 'Defer' },
    ],
    helperText: 'Change the recommended action',
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

  // Fleet utilization % — compute from decisions that have the field
  const utilizations = decisions
    .map((d) => Number(d.fleet_utilization_pct))
    .filter((v) => !isNaN(v));
  const avgUtil =
    utilizations.length > 0
      ? (utilizations.reduce((s, v) => s + v, 0) / utilizations.length).toFixed(1)
      : '0.0';

  // Surplus locations (unique source facilities with surplus > 0)
  const surplusLocations = new Set(
    decisions
      .filter((d) => d.source_surplus != null && Number(d.source_surplus) > 0)
      .map((d) => d.source_facility_id)
  ).size;

  // Deficit locations (unique target facilities with deficit > 0)
  const deficitLocations = new Set(
    decisions
      .filter((d) => d.target_deficit != null && Number(d.target_deficit) > 0)
      .map((d) => d.target_facility_id)
  ).size;

  return [
    {
      title: 'Pending Repositions',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'Fleet Utilization %',
      value: `${avgUtil}%`,
      color: Number(avgUtil) < 70 ? '#d32f2f' : '#2e7d32',
      subtitle: 'Average fleet utilization',
    },
    {
      title: 'Surplus Locations',
      value: surplusLocations,
      color: surplusLocations > 0 ? '#1565c0' : '#2e7d32',
      subtitle: `${surplusLocations} facilities with surplus`,
    },
    {
      title: 'Deficit Locations',
      value: deficitLocations,
      color: deficitLocations > 0 ? '#d32f2f' : '#2e7d32',
      subtitle: `${deficitLocations} facilities with deficit`,
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const EquipmentRepositionWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const location = useLocation();
  const initialStatusFilter = location.state?.filters?.status;
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_equipment_reposition_worklist');
  const { formatSite, loadLookupsForConfig } = useDisplayPreferences();

  useEffect(() => { loadLookupsForConfig(configId); }, [configId, loadLookupsForConfig]);

  // Memoize columns with display preference resolvers
  const columns = useMemo(() => COLUMNS.map((col) => {
    if (col.key === 'source_facility_id') {
      return { ...col, render: (d) => (
        <Typography variant="body2" fontWeight="medium">{formatSite(d.source_facility_id, d.source_facility_name) || '—'}</Typography>
      )};
    }
    if (col.key === 'target_facility_id') {
      return { ...col, render: (d) => (
        <Typography variant="body2" fontWeight="medium">{formatSite(d.target_facility_id, d.target_facility_name) || '—'}</Typography>
      )};
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
      <RoleTimeSeries roleKey="equipment_reposition" compact className="mb-4" />
      {/* Header */}
      <Box
        display="flex"
        justifyContent="space-between"
        alignItems="center"
        mb={3}
      >
        <Box>
          <Typography variant="h5" gutterBottom>
            Equipment Reposition Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review empty container and trailer repositioning recommendations from the AI agent.
            Accept, override with reason, or reject each decision before
            execution.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_equipment_reposition_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Equipment Reposition Worklist"
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

export default EquipmentRepositionWorklistPage;
