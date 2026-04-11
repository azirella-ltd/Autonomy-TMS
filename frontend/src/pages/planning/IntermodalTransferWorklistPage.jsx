/**
 * Intermodal Transfer Worklist Page
 *
 * Dedicated worklist for the Intermodal Coordinator — human counterpart of the
 * Intermodal Transfer TRM. The TRM recommends cross-mode transfer decisions
 * (MODE_SHIFT / HOLD / DEFER) and the coordinator reviews them via the shared
 * @azirella-ltd/autonomy-frontend <DecisionStream>, scoped with `filterByType="intermodal_transfer"`.
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

const TRM_TYPE = 'intermodal_transfer';
const DEFAULT_CONFIG_ID = 1;

// ---------------------------------------------------------------------------
// Summary cards builder — TMS-specific MUI cards above the shared stream
// ---------------------------------------------------------------------------

const buildSummaryCards = (decisions) => {
  if (!decisions || decisions.length === 0) {
    return [
      { title: 'Mode Shift Opportunities', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Avg Cost Savings %', value: '—', color: '#9e9e9e', subtitle: 'No data' },
      { title: 'Rail Capacity', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Avg Reliability', value: '—', color: '#9e9e9e', subtitle: 'No data' },
    ];
  }

  const modeShiftCount = decisions.filter((d) => d.recommended_action === 'MODE_SHIFT').length;

  // Avg cost savings %
  const savings = decisions
    .map((d) => Number(d.cost_savings_pct))
    .filter((v) => !isNaN(v));
  const avgSavings =
    savings.length > 0
      ? (savings.reduce((s, v) => s + v, 0) / savings.length).toFixed(1)
      : null;

  // Rail capacity available count
  const railAvailable = decisions.filter((d) => d.rail_capacity_available).length;

  // Avg reliability
  const reliabilities = decisions
    .map((d) => Number(d.intermodal_reliability_pct))
    .filter((v) => !isNaN(v));
  const avgReliability =
    reliabilities.length > 0
      ? (reliabilities.reduce((s, v) => s + v, 0) / reliabilities.length).toFixed(1)
      : null;

  return [
    {
      title: 'Mode Shift Opportunities',
      value: modeShiftCount,
      color: modeShiftCount > 0 ? '#1565c0' : '#2e7d32',
      subtitle: `${modeShiftCount} recommended shifts`,
    },
    {
      title: 'Avg Cost Savings %',
      value: avgSavings != null ? `${avgSavings}%` : '—',
      color: avgSavings == null ? '#9e9e9e' : '#2e7d32',
      subtitle: avgSavings != null ? 'Average savings from mode shift' : 'No savings data',
    },
    {
      title: 'Rail Capacity',
      value: railAvailable,
      color: railAvailable > 0 ? '#2e7d32' : '#d32f2f',
      subtitle: `${railAvailable} with rail available`,
    },
    {
      title: 'Avg Reliability',
      value: avgReliability != null ? `${avgReliability}%` : '—',
      color:
        avgReliability == null
          ? '#9e9e9e'
          : Number(avgReliability) < 85
            ? '#d32f2f'
            : '#2e7d32',
      subtitle: avgReliability != null ? 'Intermodal reliability score' : 'No reliability data',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const IntermodalTransferWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_intermodal_transfer_worklist');
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
      <RoleTimeSeries roleKey="intermodal_transfer" compact className="mb-4" />

      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Intermodal Transfer Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review cross-mode transfer decisions from the AI agent.
            Inspect, override with reason, or let the agent action stand.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_intermodal_transfer_worklist</strong> capability.
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
        emptyMessage="No intermodal transfer decisions to review"
      />
    </Box>
  );
};

export default IntermodalTransferWorklistPage;
