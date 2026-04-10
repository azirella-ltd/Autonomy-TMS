/**
 * Capacity Promise Worklist Page
 *
 * Dedicated worklist for the Capacity Promise Analyst — human counterpart of the
 * Capacity Promise TRM. The TRM recommends lane capacity commitment decisions
 * (ACCEPT / DEFER / ESCALATE) and the analyst reviews them via the shared
 * @autonomy/ui-core <DecisionStream>, scoped with `filterByType="capacity_promise"`.
 *
 * Override reasons and values flow through the shared DecisionCard's
 * Inspect → Override flow, then through tmsDecisionStreamClient to the
 * TMS backend, which records them to the TRM replay buffer (is_expert=True)
 * for reinforcement learning.
 *
 * This is the **Phase 2 reference** for the other 10 TMS worklist pages:
 *   - Page chrome (RoleTimeSeries, header, capability gating, summary cards) stays here
 *   - AIIO filter bar + decision cards + override flow come from <DecisionStream>
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Box, Typography, Alert, Grid, Card, CardContent } from '@mui/material';
import { DecisionStream } from '@autonomy/ui-core';

import LayerModeIndicator from '../../components/cascade/LayerModeIndicator';
import RoleTimeSeries from '../../components/charts/RoleTimeSeries';
import { getTRMDecisions } from '../../services/planningCascadeApi';
import { useCapabilities } from '../../hooks/useCapabilities';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';

const TRM_TYPE = 'capacity_promise';
const DEFAULT_CONFIG_ID = 1;

// ---------------------------------------------------------------------------
// Summary cards builder — TMS-specific MUI cards above the shared stream
// ---------------------------------------------------------------------------

const buildSummaryCards = (decisions) => {
  if (!decisions || decisions.length === 0) {
    return [
      { title: 'Pending Promises', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Avg Utilization %', value: '—', color: '#9e9e9e', subtitle: 'No data' },
      { title: 'Capacity Gaps', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Promise Rate', value: '—', color: '#9e9e9e', subtitle: 'No data' },
    ];
  }

  const proposed = decisions.filter((d) => d.status === 'INFORMED');
  const pendingCount = proposed.length;

  const utilizationValues = decisions.filter((d) => d.utilization_pct != null);
  const avgUtilization =
    utilizationValues.length > 0
      ? (
          (utilizationValues.reduce((sum, d) => sum + Number(d.utilization_pct), 0) /
            utilizationValues.length) *
          100
        ).toFixed(1)
      : null;

  const gapCount = decisions.filter(
    (d) =>
      d.available_capacity != null &&
      d.requested_loads != null &&
      Number(d.available_capacity) < Number(d.requested_loads)
  ).length;

  const acceptedCount = decisions.filter((d) => d.recommended_action === 'ACCEPT').length;
  const promiseRate =
    decisions.length > 0 ? ((acceptedCount / decisions.length) * 100).toFixed(1) : null;

  return [
    {
      title: 'Pending Promises',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'Avg Utilization %',
      value: avgUtilization != null ? `${avgUtilization}%` : '—',
      color:
        avgUtilization == null
          ? '#9e9e9e'
          : Number(avgUtilization) > 90
            ? '#d32f2f'
            : Number(avgUtilization) > 70
              ? '#ed6c02'
              : '#2e7d32',
      subtitle: avgUtilization != null ? 'Across all lanes' : 'No utilization data',
    },
    {
      title: 'Capacity Gaps',
      value: gapCount,
      color: gapCount > 0 ? '#d32f2f' : '#2e7d32',
      subtitle: `${gapCount} lanes under capacity`,
    },
    {
      title: 'Promise Rate',
      value: promiseRate != null ? `${promiseRate}%` : '—',
      color:
        promiseRate == null
          ? '#9e9e9e'
          : Number(promiseRate) > 80
            ? '#2e7d32'
            : '#ed6c02',
      subtitle:
        promiseRate != null
          ? `${acceptedCount} of ${decisions.length} decisions`
          : 'No decisions to score',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const CapacityPromiseWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_capacity_promise_worklist');
  const { loadLookupsForConfig } = useDisplayPreferences();

  const [summaryDecisions, setSummaryDecisions] = useState([]);
  const [summaryError, setSummaryError] = useState(null);

  useEffect(() => {
    loadLookupsForConfig(configId);
  }, [configId, loadLookupsForConfig]);

  // Fetch decision data for the summary cards. The shared <DecisionStream>
  // does its own digest fetch — this is a separate, lighter call scoped to
  // the TRM type, used only for the four KPI cards above the stream.
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
      <RoleTimeSeries roleKey="capacity_promise" compact className="mb-4" />

      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Capacity Promise Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review lane capacity commitment recommendations from the AI agent.
            Inspect, override with reason, or let the agent action stand.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_capacity_promise_worklist</strong> capability.
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
        emptyMessage="No capacity promise decisions to review"
      />
    </Box>
  );
};

export default CapacityPromiseWorklistPage;
