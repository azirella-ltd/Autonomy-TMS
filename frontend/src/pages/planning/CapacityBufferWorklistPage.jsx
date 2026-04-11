/**
 * Capacity Buffer Worklist Page
 *
 * Dedicated worklist for the Capacity Buffer Analyst — human counterpart of the
 * Capacity Buffer TRM. The TRM recommends reserve carrier capacity decisions
 * and the analyst reviews them via the shared @azirella-ltd/autonomy-frontend
 * <DecisionStream>, scoped with `filterByType="capacity_buffer"`.
 *
 * Override reasons and values flow through the shared DecisionCard's
 * Inspect → Override flow, then through tmsDecisionStreamClient to the
 * TMS backend, which records them to the TRM replay buffer (is_expert=True)
 * for reinforcement learning.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Box, Typography, Alert, Grid, Card, CardContent } from '@mui/material';
import { DecisionStream } from '@azirella-ltd/autonomy-frontend';

import LayerModeIndicator from '../../components/cascade/LayerModeIndicator';
import RoleTimeSeries from '../../components/charts/RoleTimeSeries';
import { getTRMDecisions } from '../../services/planningCascadeApi';
import { useCapabilities } from '../../hooks/useCapabilities';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';

const TRM_TYPE = 'capacity_buffer';
const DEFAULT_CONFIG_ID = 1;

// ---------------------------------------------------------------------------
// Summary cards builder — TMS-specific MUI cards above the shared stream
// ---------------------------------------------------------------------------

const buildSummaryCards = (decisions) => {
  if (!decisions || decisions.length === 0) {
    return [
      { title: 'Lanes Buffered', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Avg Buffer %', value: '—', color: '#9e9e9e', subtitle: 'No data' },
      { title: 'Capacity Gaps', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Tender Reject Rate', value: '—', color: '#9e9e9e', subtitle: 'No data' },
    ];
  }

  // Lanes with buffer > 0
  const bufferedCount = decisions.filter(
    (d) => d.buffer_loads != null && Number(d.buffer_loads) > 0
  ).length;

  // Avg buffer %
  const bufferPctValues = decisions.filter(
    (d) => d.buffer_loads != null && d.forecast_loads != null && Number(d.forecast_loads) > 0
  );
  const avgBufferPct =
    bufferPctValues.length > 0
      ? (
          (bufferPctValues.reduce(
            (sum, d) => sum + Number(d.buffer_loads) / Number(d.forecast_loads),
            0
          ) /
            bufferPctValues.length) *
          100
        ).toFixed(1)
      : null;

  // Capacity gaps (where buffer is 0 but reject rate is high)
  const gapCount = decisions.filter(
    (d) =>
      (d.buffer_loads == null || Number(d.buffer_loads) === 0) &&
      d.recent_tender_reject_rate != null &&
      Number(d.recent_tender_reject_rate) > 0.1
  ).length;

  // Avg tender reject rate
  const rejectValues = decisions.filter((d) => d.recent_tender_reject_rate != null);
  const avgRejectRate =
    rejectValues.length > 0
      ? (
          (rejectValues.reduce((sum, d) => sum + Number(d.recent_tender_reject_rate), 0) /
            rejectValues.length) *
          100
        ).toFixed(1)
      : null;

  return [
    {
      title: 'Lanes Buffered',
      value: bufferedCount,
      color: '#1565c0',
      subtitle: `${bufferedCount} of ${decisions.length} lanes`,
    },
    {
      title: 'Avg Buffer %',
      value: avgBufferPct != null ? `${avgBufferPct}%` : '—',
      color:
        avgBufferPct == null
          ? '#9e9e9e'
          : Number(avgBufferPct) > 30
            ? '#ed6c02'
            : '#1565c0',
      subtitle: avgBufferPct != null ? 'Buffer as % of forecast' : 'No buffer data',
    },
    {
      title: 'Capacity Gaps',
      value: gapCount,
      color: gapCount > 0 ? '#d32f2f' : '#2e7d32',
      subtitle: `${gapCount} unbuffered high-reject lanes`,
    },
    {
      title: 'Tender Reject Rate',
      value: avgRejectRate != null ? `${avgRejectRate}%` : '—',
      color:
        avgRejectRate == null
          ? '#9e9e9e'
          : Number(avgRejectRate) > 15
            ? '#d32f2f'
            : Number(avgRejectRate) > 10
              ? '#ed6c02'
              : '#2e7d32',
      subtitle: avgRejectRate != null ? 'Avg across all lanes' : 'No reject-rate data',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const CapacityBufferWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_capacity_buffer_worklist');
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
      <RoleTimeSeries roleKey="capacity_buffer" compact className="mb-4" />

      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Capacity Buffer Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review reserve carrier capacity recommendations from the AI agent.
            Inspect, override with reason, or let the agent action stand.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_capacity_buffer_worklist</strong> capability.
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
        emptyMessage="No capacity buffer decisions to review"
      />
    </Box>
  );
};

export default CapacityBufferWorklistPage;
