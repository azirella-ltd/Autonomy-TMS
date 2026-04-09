/**
 * Shipment Tracking Worklist Page
 *
 * Dedicated worklist for the Shipment Tracking Analyst — human counterpart of the
 * Shipment Tracking TRM. The TRM recommends in-transit exception and ETA decisions
 * (REROUTE / RETENDER / HOLD / ESCALATE) and the analyst reviews, accepts,
 * overrides, or rejects each recommendation before execution.
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

const TRM_TYPE = 'shipment_tracking';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for recommended action chips */
const ACTION_COLORS = {
  REROUTE: 'warning',
  RETENDER: 'error',
  HOLD: 'default',
  ESCALATE: 'error',
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
    key: 'shipment_id',
    label: 'Shipment',
    render: (d) => (
      <Typography variant="body2" fontWeight="medium">
        {d.shipment_id || '—'}
      </Typography>
    ),
  },
  {
    key: 'carrier_id',
    label: 'Carrier',
    render: (d) => d.carrier_id || '—',
  },
  {
    key: 'shipment_status',
    label: 'Status',
    render: (d) => {
      const status = d.shipment_status || '—';
      return <Chip label={status} size="small" variant="outlined" />;
    },
  },
  {
    key: 'current_eta',
    label: 'Current ETA',
    render: (d) => d.current_eta || '—',
  },
  {
    key: 'miles_remaining',
    label: 'Miles Left',
    render: (d) =>
      d.miles_remaining != null
        ? Number(d.miles_remaining).toLocaleString()
        : '—',
  },
  {
    key: 'active_exceptions_count',
    label: 'Exceptions',
    render: (d) => {
      if (d.active_exceptions_count == null) return '—';
      const count = Number(d.active_exceptions_count);
      return (
        <Typography
          variant="body2"
          sx={{ color: count > 0 ? 'error.main' : 'text.primary', fontWeight: count > 0 ? 'bold' : 'normal' }}
        >
          {count}
        </Typography>
      );
    },
  },
  {
    key: 'risk_bound',
    label: 'CDT Risk',
    render: (d) => {
      if (d.risk_bound == null) return '—';
      const pct = (d.risk_bound * 100).toFixed(1);
      const color = d.risk_bound < 0.1 ? 'success' : d.risk_bound < 0.3 ? 'warning' : 'error';
      return (
        <MuiTooltip title={`P(loss > threshold) = ${pct}% from Conformal Decision Theory`} arrow>
          <Chip label={`${pct}%`} size="small" color={color} variant="outlined" />
        </MuiTooltip>
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
    key: 'eta_override',
    label: 'Override ETA',
    type: 'date',
    helperText: 'Override the estimated time of arrival',
  },
  {
    key: 'exception_action',
    label: 'Exception Action',
    type: 'text',
    options: [
      { value: 'reroute', label: 'Reroute' },
      { value: 'retender', label: 'Retender' },
      { value: 'hold', label: 'Hold' },
      { value: 'escalate', label: 'Escalate' },
    ],
    helperText: 'Select an alternative exception action',
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
  const inTransit = decisions.length;

  // At risk: risk_bound > 0.3
  const atRiskCount = decisions.filter(
    (d) => d.risk_bound != null && Number(d.risk_bound) > 0.3
  ).length;

  // Late shipments
  const lateCount = decisions.filter((d) => d.is_late === true).length;

  // Total exceptions
  const exceptionCount = decisions.reduce(
    (sum, d) => sum + (Number(d.active_exceptions_count) || 0),
    0
  );

  return [
    {
      title: 'In Transit',
      value: inTransit,
      color: '#1565c0',
      subtitle: `${inTransit} shipments tracked`,
    },
    {
      title: 'At Risk',
      value: atRiskCount,
      color: atRiskCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${atRiskCount} with risk > 30%`,
    },
    {
      title: 'Late',
      value: lateCount,
      color: lateCount > 0 ? '#d32f2f' : '#2e7d32',
      subtitle: `${lateCount} past due`,
    },
    {
      title: 'Exception Count',
      value: exceptionCount,
      color: exceptionCount > 0 ? '#d32f2f' : '#2e7d32',
      subtitle: 'Active exceptions',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const ShipmentTrackingWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const location = useLocation();
  const initialStatusFilter = location.state?.filters?.status;
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_shipment_tracking_worklist');
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
      <RoleTimeSeries roleKey="shipment_tracking" compact className="mb-4" />
      {/* Header */}
      <Box
        display="flex"
        justifyContent="space-between"
        alignItems="center"
        mb={3}
      >
        <Box>
          <Typography variant="h5" gutterBottom>
            Shipment Tracking Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review in-transit exception and ETA decisions from the AI agent.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_shipment_tracking_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Shipment Tracking Worklist"
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

export default ShipmentTrackingWorklistPage;
