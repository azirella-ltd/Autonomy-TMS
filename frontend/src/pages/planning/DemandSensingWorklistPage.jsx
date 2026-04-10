/**
 * Demand Sensing Worklist Page
 *
 * Dedicated worklist for the Demand Sensing Analyst — human counterpart of the
 * Demand Sensing TRM. The TRM recommends shipping volume forecast adjustment
 * decisions and the analyst reviews them via the shared @autonomy/ui-core
 * <DecisionStream>, scoped with `filterByType="demand_sensing"`.
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

const TRM_TYPE = 'demand_sensing';
const DEFAULT_CONFIG_ID = 1;

// ---------------------------------------------------------------------------
// Summary cards builder — TMS-specific MUI cards above the shared stream
// ---------------------------------------------------------------------------

const buildSummaryCards = (decisions) => {
  if (!decisions || decisions.length === 0) {
    return [
      { title: 'Pending Adjustments', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Avg Adjustment %', value: '—', color: '#9e9e9e', subtitle: 'No data' },
      { title: 'Active Signals', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Avg MAPE', value: '—', color: '#9e9e9e', subtitle: 'No data' },
    ];
  }

  const proposed = decisions.filter((d) => d.status === 'INFORMED');
  const pendingCount = proposed.length;

  // Avg adjustment %
  const adjustmentValues = decisions.filter(
    (d) => d.adjustment != null && d.forecast_loads != null && Number(d.forecast_loads) > 0
  );
  const avgAdjustmentPct =
    adjustmentValues.length > 0
      ? (
          (adjustmentValues.reduce(
            (sum, d) => sum + Math.abs(Number(d.adjustment)) / Number(d.forecast_loads),
            0
          ) /
            adjustmentValues.length) *
          100
        ).toFixed(1)
      : null;

  // Active signals
  const activeSignals = decisions.filter(
    (d) => d.signal_type != null && d.signal_type !== ''
  ).length;

  // Avg MAPE
  const mapeValues = decisions.filter((d) => d.forecast_mape != null);
  const avgMape =
    mapeValues.length > 0
      ? (mapeValues.reduce((sum, d) => sum + Number(d.forecast_mape), 0) / mapeValues.length).toFixed(1)
      : null;

  return [
    {
      title: 'Pending Adjustments',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'Avg Adjustment %',
      value: avgAdjustmentPct != null ? `${avgAdjustmentPct}%` : '—',
      color:
        avgAdjustmentPct == null
          ? '#9e9e9e'
          : Number(avgAdjustmentPct) > 20
            ? '#d32f2f'
            : '#1565c0',
      subtitle: avgAdjustmentPct != null ? 'Mean absolute adjustment' : 'No adjustment data',
    },
    {
      title: 'Active Signals',
      value: activeSignals,
      color: '#1565c0',
      subtitle: `${activeSignals} signals detected`,
    },
    {
      title: 'Avg MAPE',
      value: avgMape != null ? `${avgMape}%` : '—',
      color:
        avgMape == null
          ? '#9e9e9e'
          : Number(avgMape) > 15
            ? '#d32f2f'
            : Number(avgMape) > 10
              ? '#ed6c02'
              : '#2e7d32',
      subtitle: avgMape != null ? 'Forecast accuracy' : 'No MAPE data',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const DemandSensingWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_demand_sensing_worklist');
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
      <RoleTimeSeries roleKey="demand_sensing" compact className="mb-4" />

      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Demand Sensing Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review shipping volume forecast adjustment recommendations from the AI agent.
            Inspect, override with reason, or let the agent action stand.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_demand_sensing_worklist</strong> capability.
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
        emptyMessage="No demand sensing decisions to review"
      />
    </Box>
  );
};

export default DemandSensingWorklistPage;
