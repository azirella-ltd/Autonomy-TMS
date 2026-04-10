/**
 * Load Build Worklist Page
 *
 * Dedicated worklist for the Load Planner — human counterpart of the
 * Load Build TRM. The TRM recommends load consolidation and optimization
 * decisions (CONSOLIDATE / SPLIT / HOLD / EXPEDITE) and the planner reviews them
 * via the shared @autonomy/ui-core <DecisionStream>, scoped with
 * `filterByType="load_build"`.
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

const TRM_TYPE = 'load_build';
const DEFAULT_CONFIG_ID = 1;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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
// Summary cards builder — TMS-specific MUI cards above the shared stream
// ---------------------------------------------------------------------------

const buildSummaryCards = (decisions) => {
  if (!decisions || decisions.length === 0) {
    return [
      { title: 'Pending Builds', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Avg Utilization %', value: '—', color: '#9e9e9e', subtitle: 'No data' },
      { title: 'Total Savings', value: '—', color: '#9e9e9e', subtitle: 'No data' },
      { title: 'Conflict Count', value: 0, color: '#2e7d32', subtitle: 'No data' },
    ];
  }

  const proposed = decisions.filter((d) => d.status === 'INFORMED');
  const pendingCount = proposed.length;

  // Avg utilization (weight-based)
  const utilizations = decisions
    .map((d) => {
      if (d.total_weight == null || d.max_weight == null || d.max_weight === 0) return NaN;
      return (Number(d.total_weight) / Number(d.max_weight)) * 100;
    })
    .filter((v) => !isNaN(v));
  const avgUtil =
    utilizations.length > 0
      ? (utilizations.reduce((s, v) => s + v, 0) / utilizations.length).toFixed(1)
      : null;

  // Total savings
  const savingsValues = decisions.filter((d) => d.consolidation_savings != null);
  const totalSavings =
    savingsValues.length > 0
      ? savingsValues.reduce((sum, d) => sum + Number(d.consolidation_savings), 0)
      : null;

  // Conflict count
  const conflictCount = decisions.filter(
    (d) => d.has_hazmat_conflict || d.has_temp_conflict
  ).length;

  return [
    {
      title: 'Pending Builds',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'Avg Utilization %',
      value: avgUtil != null ? `${avgUtil}%` : '—',
      color:
        avgUtil == null
          ? '#9e9e9e'
          : Number(avgUtil) < 70
            ? '#d32f2f'
            : '#2e7d32',
      subtitle: avgUtil != null ? 'Average weight utilization' : 'No utilization data',
    },
    {
      title: 'Total Savings',
      value: totalSavings != null ? formatCurrency(totalSavings) : '—',
      color: totalSavings == null ? '#9e9e9e' : '#1565c0',
      subtitle: totalSavings != null ? 'Consolidation savings' : 'No savings data',
    },
    {
      title: 'Conflict Count',
      value: conflictCount,
      color: conflictCount > 0 ? '#d32f2f' : '#2e7d32',
      subtitle: `${conflictCount} loads with conflicts`,
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const LoadBuildWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_load_build_worklist');
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
      <RoleTimeSeries roleKey="load_build" compact className="mb-4" />

      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Load Build Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review load consolidation and optimization recommendations from the AI agent.
            Inspect, override with reason, or let the agent action stand.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_load_build_worklist</strong> capability.
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
        emptyMessage="No load build decisions to review"
      />
    </Box>
  );
};

export default LoadBuildWorklistPage;
