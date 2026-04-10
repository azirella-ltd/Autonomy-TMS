/**
 * Equipment Reposition Worklist Page
 *
 * Dedicated worklist for the Equipment Manager — human counterpart of the
 * Equipment Reposition TRM. The TRM recommends empty container and trailer
 * repositioning decisions (REPOSITION / HOLD / DEFER) and the manager reviews
 * them via the shared @autonomy/ui-core <DecisionStream>, scoped with
 * `filterByType="equipment_reposition"`.
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

const TRM_TYPE = 'equipment_reposition';
const DEFAULT_CONFIG_ID = 1;

// ---------------------------------------------------------------------------
// Summary cards builder — TMS-specific MUI cards above the shared stream
// ---------------------------------------------------------------------------

const buildSummaryCards = (decisions) => {
  if (!decisions || decisions.length === 0) {
    return [
      { title: 'Pending Repositions', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Fleet Utilization %', value: '—', color: '#9e9e9e', subtitle: 'No data' },
      { title: 'Surplus Locations', value: 0, color: '#2e7d32', subtitle: 'No data' },
      { title: 'Deficit Locations', value: 0, color: '#2e7d32', subtitle: 'No data' },
    ];
  }

  const proposed = decisions.filter((d) => d.status === 'INFORMED');
  const pendingCount = proposed.length;

  // Fleet utilization % — compute from decisions that have the field
  const utilizations = decisions
    .map((d) => Number(d.fleet_utilization_pct))
    .filter((v) => !isNaN(v));
  const avgUtil =
    utilizations.length > 0
      ? (utilizations.reduce((s, v) => s + v, 0) / utilizations.length).toFixed(1)
      : null;

  // Surplus locations (unique source facilities with surplus > 0)
  const surplusLocations = new Set(
    decisions
      .filter((d) => d.source_surplus != null && Number(d.source_surplus) > 0)
      .map((d) => d.source_facility_id)
  ).size;

  // Deficit locations (unique target facilities with deficit > 0)
  const deficitLocations = new Set(
    decisions
      .filter((d) => d.target_deficit != null && Number(d.target_deficit) > 0)
      .map((d) => d.target_facility_id)
  ).size;

  return [
    {
      title: 'Pending Repositions',
      value: pendingCount,
      color: pendingCount > 0 ? '#ed6c02' : '#2e7d32',
      subtitle: `${pendingCount} awaiting review`,
    },
    {
      title: 'Fleet Utilization %',
      value: avgUtil != null ? `${avgUtil}%` : '—',
      color:
        avgUtil == null
          ? '#9e9e9e'
          : Number(avgUtil) < 70
            ? '#d32f2f'
            : '#2e7d32',
      subtitle: avgUtil != null ? 'Average fleet utilization' : 'No utilization data',
    },
    {
      title: 'Surplus Locations',
      value: surplusLocations,
      color: surplusLocations > 0 ? '#1565c0' : '#2e7d32',
      subtitle: `${surplusLocations} facilities with surplus`,
    },
    {
      title: 'Deficit Locations',
      value: deficitLocations,
      color: deficitLocations > 0 ? '#d32f2f' : '#2e7d32',
      subtitle: `${deficitLocations} facilities with deficit`,
    },
  ];
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const EquipmentRepositionWorklistPage = ({ configId = DEFAULT_CONFIG_ID }) => {
  const { hasCapability, loading: capLoading } = useCapabilities();
  const canManage = hasCapability('manage_equipment_reposition_worklist');
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
      <RoleTimeSeries roleKey="equipment_reposition" compact className="mb-4" />

      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Equipment Reposition Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review empty container and trailer repositioning recommendations from the AI agent.
            Inspect, override with reason, or let the agent action stand.
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      {!canManage && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have read-only access to this worklist. Contact your Customer Admin
          to request the <strong>manage_equipment_reposition_worklist</strong> capability.
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
        emptyMessage="No equipment reposition decisions to review"
      />
    </Box>
  );
};

export default EquipmentRepositionWorklistPage;
