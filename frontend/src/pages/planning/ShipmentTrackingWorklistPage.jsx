/**
 * Shipment Tracking Worklist Page
 *
 * Dedicated worklist for the Shipment Tracking Analyst -- human counterpart of the
 * Shipment Tracking TRM. The TRM recommends in-transit exception and ETA decisions
 * (REROUTE / RETENDER / HOLD / ESCALATE) and the analyst reviews, accepts,
 * overrides, or rejects each recommendation before execution.
 *
 * Override reasons and values are recorded to the TRM replay buffer
 * (is_expert=True) for reinforcement learning.
 *
 * Vendor-informed additions (project44 ETA pattern):
 * - Conformal prediction ETA display: P10/P50/P90 range bar
 * - Disruption risk indicator (weather, port congestion, carrier reliability)
 * - Carrier historical on-time performance
 * - Avg ETA Confidence summary card
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

/** Disruption risk thresholds */
const RISK_THRESHOLDS = { LOW: 0.3, MEDIUM: 0.6 };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a number as USD currency.
 */
const formatCurrency = (value) => {
  if (value == null || isNaN(value)) return '\u2014';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

/**
 * Compute a composite disruption score from individual risk factors.
 * Returns a value between 0 and 1.
 */
const computeDisruptionScore = (d) => {
  const factors = [d.weather_risk, d.port_congestion_risk, d.carrier_reliability_risk].filter(
    (v) => v != null
  );
  if (factors.length === 0) return null;
  return factors.reduce((sum, v) => sum + Number(v), 0) / factors.length;
};

/**
 * Compute the ETA confidence width in hours (P90 - P10).
 */
const etaConfidenceHours = (d) => {
  if (d.eta_p10 == null || d.eta_p90 == null) return null;
  const p10 = new Date(d.eta_p10).getTime();
  const p90 = new Date(d.eta_p90).getTime();
  if (isNaN(p10) || isNaN(p90)) return null;
  return Math.max(0, (p90 - p10) / (1000 * 60 * 60));
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * ETA Range Bar: visual P10-P50-P90 conformal prediction display.
 * Narrow bar = high confidence, wide bar = low confidence.
 */
const ETARangeBar = ({ eta_p10, eta_p50, eta_p90 }) => {
  if (eta_p10 == null || eta_p90 == null) {
    return <Typography variant="body2" color="text.secondary">{'\u2014'}</Typography>;
  }

  const p10 = new Date(eta_p10);
  const p50 = eta_p50 ? new Date(eta_p50) : null;
  const p90 = new Date(eta_p90);

  if (isNaN(p10.getTime()) || isNaN(p90.getTime())) {
    return <Typography variant="body2" color="text.secondary">{'\u2014'}</Typography>;
  }

  const rangeMs = p90.getTime() - p10.getTime();
  const rangeHours = rangeMs / (1000 * 60 * 60);

  // Bar color based on confidence width
  let barColor = '#2e7d32'; // green = tight
  if (rangeHours > 12) barColor = '#d32f2f'; // red = wide
  else if (rangeHours > 6) barColor = '#ed6c02'; // amber = moderate

  // Position of P50 within the bar (0-100%)
  let p50Pct = 50;
  if (p50 && !isNaN(p50.getTime()) && rangeMs > 0) {
    p50Pct = Math.max(0, Math.min(100, ((p50.getTime() - p10.getTime()) / rangeMs) * 100));
  }

  const formatShort = (d) => {
    try {
      return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch {
      return '\u2014';
    }
  };

  return (
    <MuiTooltip
      title={`P10: ${formatShort(p10)} | P50: ${p50 ? formatShort(p50) : '\u2014'} | P90: ${formatShort(p90)} | Range: ${rangeHours.toFixed(1)}h`}
      arrow
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, minWidth: 120 }}>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem', whiteSpace: 'nowrap' }}>
          {formatShort(p10)}
        </Typography>
        <Box sx={{ flex: 1, position: 'relative', height: 8, bgcolor: '#e0e0e0', borderRadius: 1, minWidth: 40 }}>
          <Box
            sx={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              bgcolor: barColor,
              borderRadius: 1,
              opacity: 0.3,
            }}
          />
          {/* P50 marker */}
          <Box
            sx={{
              position: 'absolute',
              top: -1,
              left: `${p50Pct}%`,
              width: 4,
              height: 10,
              bgcolor: barColor,
              borderRadius: 0.5,
              transform: 'translateX(-50%)',
            }}
          />
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem', whiteSpace: 'nowrap' }}>
          {formatShort(p90)}
        </Typography>
      </Box>
    </MuiTooltip>
  );
};

/**
 * Disruption risk badge combining weather, port congestion, and carrier reliability.
 */
const DisruptionBadge = ({ d }) => {
  const score = computeDisruptionScore(d);
  if (score == null) return <Typography variant="body2" color="text.secondary">{'\u2014'}</Typography>;

  let color = 'success';
  let label = 'LOW';
  if (score >= RISK_THRESHOLDS.MEDIUM) {
    color = 'error';
    label = 'HIGH';
  } else if (score >= RISK_THRESHOLDS.LOW) {
    color = 'warning';
    label = 'MED';
  }

  const factors = [];
  if (d.weather_risk != null) factors.push(`Weather: ${(d.weather_risk * 100).toFixed(0)}%`);
  if (d.port_congestion_risk != null) factors.push(`Port: ${(d.port_congestion_risk * 100).toFixed(0)}%`);
  if (d.carrier_reliability_risk != null) factors.push(`Carrier: ${(d.carrier_reliability_risk * 100).toFixed(0)}%`);

  return (
    <MuiTooltip title={factors.length > 0 ? factors.join(' | ') : 'No disruption data'} arrow>
      <Chip label={label} size="small" color={color} variant="outlined" />
    </MuiTooltip>
  );
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
        {d.shipment_id || '\u2014'}
      </Typography>
    ),
  },
  {
    key: 'carrier_id',
    label: 'Carrier',
    render: (d) => d.carrier_id || '\u2014',
  },
  {
    key: 'shipment_status',
    label: 'Status',
    render: (d) => {
      const status = d.shipment_status || '\u2014';
      return <Chip label={status} size="small" variant="outlined" />;
    },
  },
  {
    key: 'eta_range',
    label: 'ETA (P10 / P50 / P90)',
    render: (d) => (
      <ETARangeBar
        eta_p10={d.eta_p10}
        eta_p50={d.current_eta}
        eta_p90={d.eta_p90}
      />
    ),
  },
  {
    key: 'current_eta',
    label: 'Current ETA (P50)',
    render: (d) => d.current_eta || '\u2014',
  },
  {
    key: 'miles_remaining',
    label: 'Miles Left',
    render: (d) =>
      d.miles_remaining != null
        ? Number(d.miles_remaining).toLocaleString()
        : '\u2014',
  },
  {
    key: 'disruption_risk',
    label: 'Disruption Risk',
    render: (d) => <DisruptionBadge d={d} />,
  },
  {
    key: 'carrier_otp_pct',
    label: 'Carrier OTP %',
    render: (d) => {
      if (d.carrier_otp_pct == null) return '\u2014';
      const pct = Number(d.carrier_otp_pct);
      const color = pct >= 95 ? 'success' : pct >= 85 ? 'warning' : 'error';
      return (
        <MuiTooltip title={`Carrier historical on-time performance: ${pct.toFixed(1)}%`} arrow>
          <Chip label={`${pct.toFixed(1)}%`} size="small" color={color} variant="outlined" />
        </MuiTooltip>
      );
    },
  },
  {
    key: 'active_exceptions_count',
    label: 'Exceptions',
    render: (d) => {
      if (d.active_exceptions_count == null) return '\u2014';
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
      if (d.risk_bound == null) return '\u2014';
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
      const action = d.recommended_action || '\u2014';
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

  // Avg ETA Confidence: average width of P10-P90 range in hours
  const confidenceValues = decisions
    .map((d) => etaConfidenceHours(d))
    .filter((v) => v != null);
  const avgConfidence = confidenceValues.length > 0
    ? confidenceValues.reduce((sum, v) => sum + v, 0) / confidenceValues.length
    : null;

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
    {
      title: 'Avg ETA Confidence',
      value: avgConfidence != null ? `${avgConfidence.toFixed(1)}h` : '\u2014',
      color: avgConfidence != null && avgConfidence > 12 ? '#d32f2f' : avgConfidence != null && avgConfidence > 6 ? '#ed6c02' : '#2e7d32',
      subtitle: avgConfidence != null ? 'P10-P90 range width' : 'No conformal ETA data',
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
