/**
 * Broker Routing Worklist Page
 *
 * Dedicated worklist for the Broker Routing Analyst — human counterpart of the
 * Broker Routing TRM. The TRM recommends broker vs asset carrier routing decisions
 * (ROUTE_BROKER / HOLD / ESCALATE) and the analyst reviews, accepts,
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

const TRM_TYPE = 'broker_routing';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for recommended action chips */
const ACTION_COLORS = {
  ROUTE_BROKER: 'info',
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
    key: 'load_id',
    label: 'Load',
    render: (d) => (
      <Typography variant="body2" fontWeight="medium">
        {d.load_id || '—'}
      </Typography>
    ),
  },
  {
    key: 'lane_id',
    label: 'Lane',
    render: (d) => d.lane_id || '—',
  },
  {
    key: 'mode',
    label: 'Mode',
    render: (d) => d.mode || '—',
  },
  {
    key: 'tender_attempts_exhausted',
    label: 'Carriers Declined',
    render: (d) => (
      <Chip
        label={d.tender_attempts_exhausted ? 'Yes' : 'No'}
        size="small"
        color={d.tender_attempts_exhausted ? 'error' : 'default'}
        variant="outlined"
      />
    ),
  },
  {
    key: 'hours_to_pickup',
    label: 'Hours to Pickup',
    render: (d) => {
      if (d.hours_to_pickup == null) return '—';
      const val = Number(d.hours_to_pickup);
      const color = val < 12 ? '#d32f2f' : 'inherit';
      return (
        <Typography variant="body2" sx={{ color, fontWeight: val < 12 ? 'bold' : 'normal' }}>
          {val.toFixed(1)}
        </Typography>
      );
    },
  },
  {
    key: 'broker_rate_premium_pct',
    label: 'Premium %',
    render: (d) => {
      if (d.broker_rate_premium_pct == null) return '—';
      return `${Number(d.broker_rate_premium_pct).toFixed(1)}%`;
    },
  },
  {
    key: 'shipment_priority',
    label: 'Priority',
    render: (d) => {
      const priority = d.shipment_priority || '—';
      return <Chip label={priority} size="small" variant="outlined" />;
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
    key: 'broker_id',
    label: 'Preferred Broker',
    type: 'text',
    helperText: 'Specify preferred broker',
  },
  {
    key: 'max_rate',
    label: 'Max Rate',
    type: 'number',
    helperText: 'Maximum acceptable rate in dollars',
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
  const brokerCount = decisions.filter(
    (d) => d.recommended_action === 'ROUTE_BROKER'
  ).length;

  // Avg premium %
  const premiums = decisions
    .map((d) => Number(d.broker_rate_premium_pct))
    .filter((v) => !isNaN(v));
  const avgPremium =
    premiums.length > 0
      ? (premiums.reduce((s, v) => s + v, 0) / premiums.length).toFixed(1)
      : '0.0';

  // Budget remaining (sum of max_rate - broker_rate for proposed)
  const budgetRemaining = proposed.reduce(
    (sum, d) => sum + (Number(d.budget_remaining) || 0),
    0
  );

  // Avg reliability
  const reliabilities = decisions
    .map((d) => Number(d.broker_reliability_pct))
    .filter((v) => !isNaN(v));
  const avgReliability =
    reliabilities.length > 0
      ? (reliabilities.reduce((s, v) => s + v, 0) / reliabilities.length).toFixed(1)
      : '0.0';

  return [
    {
      title: 'Broker Loads',
      value: brokerCount,
      color: brokerCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${brokerCount} routed to broker`,
    },
    {
      title: 'Avg Premium %',
      value: `${avgPremium}%`,
      color: Number(avgPremium) > 15 ? '#d32f2f' : '#2e7d32',
      subtitle: 'Broker rate premium',
    },
    {
      title: 'Budget Remaining',
      value: formatCurrency(budgetRemaining),
      color: '#1565c0',
      subtitle: 'Remaining broker budget',
    },
    {
      title: 'Avg Reliability',
      value: `${avgReliability}%`,
      color: Number(avgReliability) < 85 ? '#d32f2f' : '#2e7d32',
      subtitle: 'Broker reliability score',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const BrokerRoutingWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const location = useLocation();
  const initialStatusFilter = location.state?.filters?.status;
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_broker_routing_worklist');
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
      <RoleTimeSeries roleKey="broker_routing" compact className="mb-4" />
      {/* Header */}
      <Box
        display="flex"
        justifyContent="space-between"
        alignItems="center"
        mb={3}
      >
        <Box>
          <Typography variant="h5" gutterBottom>
            Broker Routing Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review broker vs asset carrier routing decisions from the AI agent.
            Accept, override with reason, or reject each decision before
            execution.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_broker_routing_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="Broker Routing Worklist"
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

export default BrokerRoutingWorklistPage;
