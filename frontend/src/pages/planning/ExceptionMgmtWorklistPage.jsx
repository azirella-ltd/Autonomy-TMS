/**
 * Exception Management Worklist Page
 *
 * Dedicated worklist for the Exception Management Analyst — human counterpart of the
 * Exception Management TRM. The TRM recommends delay, damage, and refusal resolution
 * decisions (RETENDER / REROUTE / PARTIAL_DELIVER / ESCALATE / WRITE_OFF) and the
 * analyst reviews them via the shared @autonomy/ui-core <DecisionStream>, scoped with
 * `filterByType="exception_management"`.
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

const TRM_TYPE = 'exception_management';
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
      { title: 'Open Exceptions', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Critical Count', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Avg Resolution Hours', value: '—', color: '#9e9e9e', subtitle: 'No data' },
      { title: 'Total Cost Impact', value: '—', color: '#9e9e9e', subtitle: 'No data' },
    ];
  }

  const openCount = decisions.length;

  const criticalCount = decisions.filter((d) => d.severity === 'CRITICAL').length;

  const hoursValues = decisions.filter((d) => d.hours_since_detected != null);
  const avgHours =
    hoursValues.length > 0
      ? (hoursValues.reduce((sum, d) => sum + Number(d.hours_since_detected), 0) / hoursValues.length).toFixed(1)
      : null;

  const costValues = decisions.filter((d) => d.estimated_cost_impact != null);
  const totalCost =
    costValues.length > 0
      ? costValues.reduce((sum, d) => sum + Number(d.estimated_cost_impact), 0)
      : null;

  return [
    {
      title: 'Open Exceptions',
      value: openCount,
      color: openCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${openCount} requiring action`,
    },
    {
      title: 'Critical Count',
      value: criticalCount,
      color: criticalCount > 0 ? '#d32f2f' : '#2e7d32',
      subtitle: `${criticalCount} critical severity`,
    },
    {
      title: 'Avg Resolution Hours',
      value: avgHours != null ? avgHours : '—',
      color:
        avgHours == null
          ? '#9e9e9e'
          : Number(avgHours) > 24
            ? '#d32f2f'
            : Number(avgHours) > 8
              ? '#ed6c02'
              : '#2e7d32',
      subtitle: avgHours != null ? 'Hours since detection' : 'No resolution-time data',
    },
    {
      title: 'Total Cost Impact',
      value: totalCost != null ? formatCurrency(totalCost) : '—',
      color:
        totalCost == null
          ? '#9e9e9e'
          : totalCost > 50000
            ? '#d32f2f'
            : totalCost > 10000
              ? '#ed6c02'
              : '#1565c0',
      subtitle: totalCost != null ? 'Estimated financial impact' : 'No cost-impact data',
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const ExceptionMgmtWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_exception_mgmt_worklist');
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
      <RoleTimeSeries roleKey="exception_management" compact className="mb-4" />

      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Exception Management Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review delay, damage, and refusal resolution recommendations from the AI agent.
            Inspect, override with reason, or let the agent action stand.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_exception_mgmt_worklist</strong> capability.
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
        emptyMessage="No exception management decisions to review"
      />
    </Box>
  );
};

export default ExceptionMgmtWorklistPage;
