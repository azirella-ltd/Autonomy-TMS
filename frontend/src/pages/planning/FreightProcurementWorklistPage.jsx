/**
 * Freight Procurement Worklist Page
 *
 * Dedicated worklist for the Freight Procurement Analyst — human counterpart of the
 * Freight Procurement TRM. The TRM recommends carrier waterfall tendering decisions
 * (TENDER / DEFER / SPOT / BROKER) and the analyst reviews them via the shared
 * @autonomy/ui-core <DecisionStream>, scoped with `filterByType="freight_procurement"`.
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

const TRM_TYPE = 'freight_procurement';
const DEFAULT_CONFIG_ID = 1;

// ---------------------------------------------------------------------------
// Summary cards builder — TMS-specific MUI cards above the shared stream
// ---------------------------------------------------------------------------

const buildSummaryCards = (decisions) => {
  if (!decisions || decisions.length === 0) {
    return [
      { title: 'Pending Tenders', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Avg Rate vs Benchmark', value: '—', color: '#9e9e9e', subtitle: 'No data' },
      { title: 'Accept Rate', value: '—', color: '#9e9e9e', subtitle: 'No data' },
      { title: 'Avg Hours to Deadline', value: '—', color: '#9e9e9e', subtitle: 'No data' },
    ];
  }

  const proposed = decisions.filter((d) => d.status === 'INFORMED');
  const pendingCount = proposed.length;

  // Avg rate vs benchmark %
  const rateComps = decisions.filter(
    (d) => d.primary_carrier_rate != null && d.dat_benchmark_rate != null && Number(d.dat_benchmark_rate) > 0
  );
  const avgRateVsBenchmark =
    rateComps.length > 0
      ? (
          (rateComps.reduce(
            (sum, d) => sum + Number(d.primary_carrier_rate) / Number(d.dat_benchmark_rate),
            0
          ) /
            rateComps.length) *
          100
        ).toFixed(1)
      : null;

  // Accept rate (TENDER actions)
  const tenderCount = decisions.filter((d) => d.recommended_action === 'TENDER').length;
  const acceptRate =
    decisions.length > 0 ? ((tenderCount / decisions.length) * 100).toFixed(1) : null;

  // Avg hours to deadline
  const deadlineValues = decisions.filter((d) => d.hours_to_tender_deadline != null);
  const avgHours =
    deadlineValues.length > 0
      ? (deadlineValues.reduce((sum, d) => sum + Number(d.hours_to_tender_deadline), 0) / deadlineValues.length).toFixed(1)
      : null;

  return [
    {
      title: 'Pending Tenders',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'Avg Rate vs Benchmark',
      value: avgRateVsBenchmark != null ? `${avgRateVsBenchmark}%` : '—',
      color:
        avgRateVsBenchmark == null
          ? '#9e9e9e'
          : Number(avgRateVsBenchmark) > 110
            ? '#d32f2f'
            : Number(avgRateVsBenchmark) > 100
              ? '#ed6c02'
              : '#2e7d32',
      subtitle: avgRateVsBenchmark != null ? 'Primary rate / benchmark' : 'No benchmark data',
    },
    {
      title: 'Accept Rate',
      value: acceptRate != null ? `${acceptRate}%` : '—',
      color:
        acceptRate == null
          ? '#9e9e9e'
          : Number(acceptRate) > 70
            ? '#2e7d32'
            : '#ed6c02',
      subtitle:
        acceptRate != null ? `${tenderCount} of ${decisions.length} decisions` : 'No decisions to score',
    },
    {
      title: 'Avg Hours to Deadline',
      value: avgHours != null ? avgHours : '—',
      color:
        avgHours == null
          ? '#9e9e9e'
          : Number(avgHours) < 8
            ? '#d32f2f'
            : Number(avgHours) < 24
              ? '#ed6c02'
              : '#2e7d32',
      subtitle: avgHours != null ? 'Time remaining to tender' : 'No deadline data',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const FreightProcurementWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_freight_procurement_worklist');
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
      <RoleTimeSeries roleKey="freight_procurement" compact className="mb-4" />

      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Freight Procurement Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review carrier waterfall tendering recommendations from the AI agent.
            Inspect, override with reason, or let the agent action stand.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_freight_procurement_worklist</strong> capability.
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
        emptyMessage="No freight procurement decisions to review"
      />
    </Box>
  );
};

export default FreightProcurementWorklistPage;
