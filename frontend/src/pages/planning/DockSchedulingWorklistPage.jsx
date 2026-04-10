/**
 * Dock Scheduling Worklist Page
 *
 * Dedicated worklist for the Dock Scheduler — human counterpart of the
 * Dock Scheduling TRM. The TRM recommends appointment and dock door optimization
 * decisions (SCHEDULE / DEFER / EXPEDITE / REJECT) and the scheduler reviews them
 * via the shared @autonomy/ui-core <DecisionStream>, scoped with
 * `filterByType="dock_scheduling"`.
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

const TRM_TYPE = 'dock_scheduling';
const DEFAULT_CONFIG_ID = 1;

// ---------------------------------------------------------------------------
// Summary cards builder — TMS-specific MUI cards above the shared stream
// ---------------------------------------------------------------------------

const buildSummaryCards = (decisions) => {
  if (!decisions || decisions.length === 0) {
    return [
      { title: 'Appointments Today', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Door Utilization %', value: '—', color: '#9e9e9e', subtitle: 'No data' },
      { title: 'Avg Dwell Minutes', value: '—', color: '#9e9e9e', subtitle: 'No data' },
      { title: 'Detention Risk Count', value: 0, color: '#2e7d32', subtitle: 'No data' },
    ];
  }

  const proposed = decisions.filter((d) => d.status === 'INFORMED');
  const appointmentCount = proposed.length;

  // Avg door utilization
  const utilizations = decisions
    .map((d) => Number(d.utilization_pct))
    .filter((v) => !isNaN(v));
  const avgUtil =
    utilizations.length > 0
      ? (utilizations.reduce((s, v) => s + v, 0) / utilizations.length).toFixed(1)
      : null;

  // Avg dwell time
  const dwells = decisions
    .map((d) => Number(d.avg_dwell_time_minutes))
    .filter((v) => !isNaN(v));
  const avgDwell =
    dwells.length > 0
      ? (dwells.reduce((s, v) => s + v, 0) / dwells.length).toFixed(0)
      : null;

  // Detention risk count (high risk)
  const detentionCount = decisions.filter(
    (d) => d.detention_risk_score != null && Number(d.detention_risk_score) >= 0.7
  ).length;

  return [
    {
      title: 'Appointments Today',
      value: appointmentCount,
      color: appointmentCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${appointmentCount} awaiting scheduling`,
    },
    {
      title: 'Door Utilization %',
      value: avgUtil != null ? `${avgUtil}%` : '—',
      color:
        avgUtil == null
          ? '#9e9e9e'
          : Number(avgUtil) > 90
            ? '#d32f2f'
            : '#2e7d32',
      subtitle: avgUtil != null ? 'Average door utilization' : 'No utilization data',
    },
    {
      title: 'Avg Dwell Minutes',
      value: avgDwell != null ? avgDwell : '—',
      color:
        avgDwell == null
          ? '#9e9e9e'
          : Number(avgDwell) > 60
            ? '#d32f2f'
            : '#2e7d32',
      subtitle: avgDwell != null ? 'Average dwell time' : 'No dwell data',
    },
    {
      title: 'Detention Risk Count',
      value: detentionCount,
      color: detentionCount > 0 ? '#d32f2f' : '#2e7d32',
      subtitle: `${detentionCount} high detention risk`,
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const DockSchedulingWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_dock_scheduling_worklist');
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
      <RoleTimeSeries roleKey="dock_scheduling" compact className="mb-4" />

      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Dock Scheduling Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review appointment and dock door optimization recommendations from the AI agent.
            Inspect, override with reason, or let the agent action stand.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_dock_scheduling_worklist</strong> capability.
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
        emptyMessage="No dock scheduling decisions to review"
      />
    </Box>
  );
};

export default DockSchedulingWorklistPage;
