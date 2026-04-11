/**
 * Broker Routing Worklist Page
 *
 * Dedicated worklist for the Broker Routing Analyst — human counterpart of the
 * Broker Routing TRM. The TRM recommends broker vs asset carrier routing decisions
 * (ROUTE_BROKER / HOLD / ESCALATE) and the analyst reviews them via the shared
 * @azirella-ltd/autonomy-frontend <DecisionStream>, scoped with `filterByType="broker_routing"`.
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

const TRM_TYPE = 'broker_routing';
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
      { title: 'Broker Loads', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Avg Premium %', value: '—', color: '#9e9e9e', subtitle: 'No data' },
      { title: 'Budget Remaining', value: '—', color: '#9e9e9e', subtitle: 'No data' },
      { title: 'Avg Reliability', value: '—', color: '#9e9e9e', subtitle: 'No data' },
    ];
  }

  const proposed = decisions.filter((d) => d.status === 'INFORMED');
  const brokerCount = decisions.filter((d) => d.recommended_action === 'ROUTE_BROKER').length;

  // Avg premium %
  const premiums = decisions
    .map((d) => Number(d.broker_rate_premium_pct))
    .filter((v) => !isNaN(v));
  const avgPremium =
    premiums.length > 0
      ? (premiums.reduce((s, v) => s + v, 0) / premiums.length).toFixed(1)
      : null;

  // Budget remaining (sum of budget_remaining across proposed decisions that have the field)
  const budgetValues = proposed.filter((d) => d.budget_remaining != null);
  const budgetRemaining =
    budgetValues.length > 0
      ? budgetValues.reduce((sum, d) => sum + Number(d.budget_remaining), 0)
      : null;

  // Avg reliability
  const reliabilities = decisions
    .map((d) => Number(d.broker_reliability_pct))
    .filter((v) => !isNaN(v));
  const avgReliability =
    reliabilities.length > 0
      ? (reliabilities.reduce((s, v) => s + v, 0) / reliabilities.length).toFixed(1)
      : null;

  return [
    {
      title: 'Broker Loads',
      value: brokerCount,
      color: brokerCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${brokerCount} routed to broker`,
    },
    {
      title: 'Avg Premium %',
      value: avgPremium != null ? `${avgPremium}%` : '—',
      color:
        avgPremium == null
          ? '#9e9e9e'
          : Number(avgPremium) > 15
            ? '#d32f2f'
            : '#2e7d32',
      subtitle: avgPremium != null ? 'Broker rate premium' : 'No premium data',
    },
    {
      title: 'Budget Remaining',
      value: budgetRemaining != null ? formatCurrency(budgetRemaining) : '—',
      color: budgetRemaining == null ? '#9e9e9e' : '#1565c0',
      subtitle: budgetRemaining != null ? 'Remaining broker budget' : 'No budget data',
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
      subtitle: avgReliability != null ? 'Broker reliability score' : 'No reliability data',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const BrokerRoutingWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_broker_routing_worklist');
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
      <RoleTimeSeries roleKey="broker_routing" compact className="mb-4" />

      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Broker Routing Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review broker vs asset carrier routing decisions from the AI agent.
            Inspect, override with reason, or let the agent action stand.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_broker_routing_worklist</strong> capability.
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
        emptyMessage="No broker routing decisions to review"
      />
    </Box>
  );
};

export default BrokerRoutingWorklistPage;
