/**
 * Shipment Tracking Worklist Page
 *
 * Dedicated worklist for the Shipment Tracking Analyst — human counterpart of the
 * Shipment Tracking TRM. The TRM recommends in-transit exception and ETA decisions
 * (REROUTE / RETENDER / HOLD / ESCALATE) and the analyst reviews them via the
 * shared @autonomy/ui-core <DecisionStream>, scoped with
 * `filterByType="shipment_tracking"`.
 *
 * Override reasons and values flow through the shared DecisionCard's
 * Inspect → Override flow, then through tmsDecisionStreamClient to the
 * TMS backend, which records them to the TRM replay buffer (is_expert=True)
 * for reinforcement learning.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Box, Typography, Alert, Grid, Card, CardContent } from '@mui/material';
import { DecisionStream } from '@autonomy/ui-core';

import LayerModeIndicator from '../../components/cascade/LayerModeIndicator';
import RoleTimeSeries from '../../components/charts/RoleTimeSeries';
import { getTRMDecisions } from '../../services/planningCascadeApi';
import { useCapabilities } from '../../hooks/useCapabilities';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';

const TRM_TYPE = 'shipment_tracking';
const DEFAULT_CONFIG_ID = 1;

// ---------------------------------------------------------------------------
// Summary cards builder — TMS-specific MUI cards above the shared stream
// ---------------------------------------------------------------------------

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

const buildSummaryCards = (decisions) => {
  if (!decisions || decisions.length === 0) {
    return [
      { title: 'In Transit', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'At Risk', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Late', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Exception Count', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Avg ETA Confidence', value: '—', color: '#9e9e9e', subtitle: 'No data' },
    ];
  }

  const inTransit = decisions.length;

  const atRiskCount = decisions.filter(
    (d) => d.risk_bound != null && Number(d.risk_bound) > 0.3
  ).length;

  const lateCount = decisions.filter((d) => d.is_late === true).length;

  const exceptionCount = decisions.reduce(
    (sum, d) => sum + (Number(d.active_exceptions_count) || 0),
    0
  );

  const confidenceValues = decisions
    .map((d) => etaConfidenceHours(d))
    .filter((v) => v != null);
  const avgConfidence =
    confidenceValues.length > 0
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
      value: avgConfidence != null ? `${avgConfidence.toFixed(1)}h` : '—',
      color:
        avgConfidence == null
          ? '#9e9e9e'
          : avgConfidence > 12
            ? '#d32f2f'
            : avgConfidence > 6
              ? '#ed6c02'
              : '#2e7d32',
      subtitle: avgConfidence != null ? 'P10-P90 range width' : 'No conformal ETA data',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const ShipmentTrackingWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_shipment_tracking_worklist');
  const { loadLookupsForConfig } = useDisplayPreferences();

  const [summaryDecisions, setSummaryDecisions] = useState([]);
  const [summaryError, setSummaryError] = useState(null);

  useEffect(() => {
    loadLookupsForConfig(configId);
  }, [configId, loadLookupsForConfig]);

  const loadSummary = useCallback(async () => {
    try {
      const data = await getTRMDecisions(configId, { trm_type: TRM_TYPE });
      setSummaryDecisions(data?.decisions || []);
      setSummaryError(null);
    } catch (err) {
      setSummaryError(err?.message || 'Failed to load summary metrics');
      setSummaryDecisions([]);
    }
  }, [configId]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  if (capLoading) {
    return null;
  }

  const cards = buildSummaryCards(summaryDecisions);

  return (
    <Box sx={{ p: 3 }}>
      <RoleTimeSeries roleKey="shipment_tracking" compact className="mb-4" />

      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Shipment Tracking Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review in-transit exception and ETA decisions from the AI agent.
            Inspect, override with reason, or let the agent action stand.
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

      {summaryError && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Summary metrics unavailable: {summaryError}
        </Alert>
      )}

      {/* TMS-specific summary cards */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {cards.map((card) => (
          <Grid item xs={12} sm={6} md={3} key={card.title}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="caption" color="text.secondary">
                  {card.title}
                </Typography>
                <Typography variant="h4" sx={{ color: card.color, mt: 0.5 }}>
                  {card.value}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {card.subtitle}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Shared Decision Stream — AIIO filter bar + cards + override flow */}
      <DecisionStream
        configId={configId}
        filterByType={TRM_TYPE}
        hideHeader
        canOverride={canManage}
        emptyMessage="No shipment tracking decisions to review"
      />
    </Box>
  );
};

export default ShipmentTrackingWorklistPage;
