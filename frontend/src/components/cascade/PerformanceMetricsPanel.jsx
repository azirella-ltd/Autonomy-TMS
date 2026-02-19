/**
 * Performance Metrics Panel
 *
 * Shows Agent Performance Score, Touchless Rate, and Human Override Rate.
 * Used in Supply Worklist and Allocation Worklist performance tabs.
 */
import React, { useState, useEffect } from 'react';
import {
  Box, Paper, Typography, Grid, Card, CardContent, CircularProgress,
} from '@mui/material';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar,
} from 'recharts';
import { getAgentMetrics } from '../../services/planningCascadeApi';

const MetricCard = ({ title, value, subtitle, color = '#1976d2' }) => (
  <Card variant="outlined">
    <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
      <Typography variant="caption" color="text.secondary">{title}</Typography>
      <Typography variant="h4" sx={{ color, fontWeight: 'bold' }}>
        {value ?? '—'}
      </Typography>
      {subtitle && (
        <Typography variant="caption" color="text.secondary">{subtitle}</Typography>
      )}
    </CardContent>
  </Card>
);

const PerformanceMetricsPanel = ({ configId, agentType = 'supply_agent' }) => {
  const [metrics, setMetrics] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadMetrics();
  }, [configId, agentType]);

  const loadMetrics = async () => {
    try {
      setLoading(true);
      const data = await getAgentMetrics(configId, agentType, 20);
      setMetrics(data.metrics || []);
    } catch (error) {
      console.error('Failed to load metrics', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={4}>
        <CircularProgress />
      </Box>
    );
  }

  const latest = metrics[0] || {};

  const formatPct = (v) => v != null ? `${(v * 100).toFixed(1)}%` : '—';
  const formatScore = (v) => v != null ? `${v > 0 ? '+' : ''}${v.toFixed(1)}` : '—';

  // Reverse for chronological order in charts
  const chartData = [...metrics].reverse().map(m => ({
    period: m.period_start,
    agentScore: m.agent_score,
    userScore: m.user_score,
    touchlessRate: m.touchless_rate ? m.touchless_rate * 100 : null,
    humanOverrideRate: m.human_override_rate ? m.human_override_rate * 100 : null,
    overrideDependency: m.override_dependency_ratio ? m.override_dependency_ratio * 100 : null,
    total: m.total_decisions,
    autoSubmitted: m.auto_submitted,
    reviewed: m.reviewed,
    overridden: m.overridden,
    rejected: m.rejected,
  }));

  return (
    <Box>
      {/* Summary Cards */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={6} md={2}>
          <MetricCard
            title="Touchless Rate"
            value={formatPct(latest.touchless_rate)}
            subtitle="% auto-submitted"
            color="#2e7d32"
          />
        </Grid>
        <Grid item xs={6} md={2}>
          <MetricCard
            title="Agent Score"
            value={formatScore(latest.agent_score)}
            subtitle="vs baseline"
            color={latest.agent_score > 0 ? '#2e7d32' : '#c62828'}
          />
        </Grid>
        <Grid item xs={6} md={2}>
          <MetricCard
            title="User Score"
            value={formatScore(latest.user_score)}
            subtitle="override lift"
            color={latest.user_score > 0 ? '#1565c0' : '#f57c00'}
          />
        </Grid>
        <Grid item xs={6} md={2}>
          <MetricCard
            title="Override Rate"
            value={formatPct(latest.human_override_rate)}
            subtitle="reviewed / total"
            color="#7b1fa2"
          />
        </Grid>
        <Grid item xs={6} md={2}>
          <MetricCard
            title="Override Ratio"
            value={formatPct(latest.override_dependency_ratio)}
            subtitle="repeated interventions"
            color="#f57c00"
          />
        </Grid>
        <Grid item xs={6} md={2}>
          <MetricCard
            title="Coherence"
            value={formatPct(latest.downstream_coherence)}
            subtitle="downstream match"
            color="#0097a7"
          />
        </Grid>
      </Grid>

      {chartData.length > 1 && (
        <Grid container spacing={2}>
          {/* Performance Score Trend */}
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2" gutterBottom>Performance Score Trend</Typography>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="period" tick={{ fontSize: 10 }} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="agentScore" stroke="#2e7d32" name="Agent Score" strokeWidth={2} />
                  <Line type="monotone" dataKey="userScore" stroke="#1565c0" name="User Score" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </Paper>
          </Grid>

          {/* Decision Volume */}
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2" gutterBottom>Decision Volume</Typography>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="period" tick={{ fontSize: 10 }} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="autoSubmitted" stackId="a" fill="#2e7d32" name="Auto-submitted" />
                  <Bar dataKey="reviewed" stackId="a" fill="#1565c0" name="Reviewed" />
                  <Bar dataKey="overridden" stackId="a" fill="#f57c00" name="Overridden" />
                  <Bar dataKey="rejected" stackId="a" fill="#c62828" name="Rejected" />
                </BarChart>
              </ResponsiveContainer>
            </Paper>
          </Grid>
        </Grid>
      )}

      {chartData.length <= 1 && (
        <Paper variant="outlined" sx={{ p: 3, textAlign: 'center' }}>
          <Typography variant="body2" color="text.secondary">
            Not enough historical data for trend charts. Metrics will appear after multiple planning cycles.
          </Typography>
        </Paper>
      )}
    </Box>
  );
};

export default PerformanceMetricsPanel;
