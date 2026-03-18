/**
 * PO Creation Worklist Page
 *
 * Dedicated worklist for the PO Analyst — human counterpart of the
 * PO Creation TRM. The TRM recommends purchase order creation decisions
 * (ORDER / DEFER / EXPEDITE / CANCEL) and the analyst reviews, accepts,
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

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TRM_TYPE = 'po_creation';
const DEFAULT_CONFIG_ID = 1;

/** Color mapping for recommended action chips */
const ACTION_COLORS = {
  ORDER: 'success',
  DEFER: 'default',
  EXPEDITE: 'warning',
  CANCEL: 'error',
};

/** Color mapping for urgency chips */
const URGENCY_COLORS = {
  CRITICAL: 'error',
  HIGH: 'warning',
  NORMAL: 'info',
  LOW: 'default',
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
 * Format days of supply with one decimal.
 */
const formatDaysOfSupply = (value) => {
  if (value == null || isNaN(value)) return '—';
  return `${Number(value).toFixed(1)} days`;
};

// ---------------------------------------------------------------------------
// Column definitions for TRMDecisionWorklist
// ---------------------------------------------------------------------------

const PO_COLUMNS = [
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
    key: 'supplier_id',
    label: 'Supplier',
    render: (d) => d.supplier_id || '—',
  },
  {
    key: 'recommended_action',
    label: 'Recommended',
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
  {
    key: 'recommended_qty',
    label: 'Order Qty',
    render: (d) =>
      d.recommended_qty != null
        ? Number(d.recommended_qty).toLocaleString()
        : '—',
  },
  {
    key: 'expected_cost',
    label: 'Expected Cost',
    render: (d) => formatCurrency(d.expected_cost),
  },
  {
    key: 'urgency',
    label: 'Urgency',
    render: (d) => {
      const urgency = d.urgency || '—';
      return (
        <Chip
          label={urgency}
          size="small"
          color={URGENCY_COLORS[urgency] || 'default'}
          variant={urgency === 'CRITICAL' ? 'filled' : 'outlined'}
        />
      );
    },
  },
  {
    key: 'days_of_supply',
    label: 'Days of Supply',
    render: (d) => formatDaysOfSupply(d.days_of_supply),
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
];

// ---------------------------------------------------------------------------
// Override field definitions for the Override Dialog
// ---------------------------------------------------------------------------

const PO_OVERRIDE_FIELDS = [
  {
    key: 'recommended_qty',
    label: 'Override Order Qty',
    type: 'number',
    helperText: 'Enter a new order quantity to replace the AI recommendation',
  },
  {
    key: 'supplier_id',
    label: 'Override Supplier',
    type: 'text',
    helperText: 'Enter an alternative supplier ID',
  },
  {
    key: 'recommended_action',
    label: 'Override Action',
    type: 'text',
    options: [
      { value: 'ORDER', label: 'ORDER' },
      { value: 'DEFER', label: 'DEFER' },
      { value: 'EXPEDITE', label: 'EXPEDITE' },
      { value: 'CANCEL', label: 'CANCEL' },
    ],
    helperText: 'Change the recommended action (ORDER, DEFER, EXPEDITE, CANCEL)',
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

  // Total spend of proposed POs
  const totalSpend = proposed.reduce(
    (sum, d) => sum + (Number(d.expected_cost) || 0),
    0
  );

  // Expedite rate: fraction of all decisions that are EXPEDITE
  const expediteCount = decisions.filter(
    (d) => d.recommended_action === 'EXPEDITE'
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
      title: 'Pending POs',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'Total Spend',
      value: formatCurrency(totalSpend),
      color: '#1565c0',
      subtitle: 'Proposed PO value',
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

const POWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const location = useLocation();
  const initialStatusFilter = location.state?.filters?.status;
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_po_worklist');
  const { formatProduct, formatSite, loadLookupsForConfig } = useDisplayPreferences();

  useEffect(() => { loadLookupsForConfig(configId); }, [configId, loadLookupsForConfig]);

  // Memoize columns with display preference resolvers
  const columns = useMemo(() => PO_COLUMNS.map((col) => {
    if (col.key === 'product_id') {
      return { ...col, render: (d) => (
        <Typography variant="body2" fontWeight="medium">{formatProduct(d.product_id, d.product_name) || '\u2014'}</Typography>
      )};
    }
    if (col.key === 'supplier_id') {
      return { ...col, render: (d) => formatSite(d.supplier_id, d.supplier_name) || '\u2014' };
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
            PO Creation Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review purchase order recommendations from the AI agent.
            Accept, override with reason, or reject each decision before
            execution.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_po_worklist</strong> capability.
        </Alert>
      )}

      {/* TRM Decision Worklist */}
      <TRMDecisionWorklist
        configId={configId}
        trmType={TRM_TYPE}
        title="PO Creation Worklist"
        columns={columns}
        overrideFields={PO_OVERRIDE_FIELDS}
        summaryCards={summaryCardsFn}
        fetchDecisions={getTRMDecisions}
        submitAction={submitTRMAction}
        canManage={canManage}
        initialStatusFilter={initialStatusFilter}
      />
    </Box>
  );
};

export default POWorklistPage;
