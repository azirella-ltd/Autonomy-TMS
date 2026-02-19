/**
 * Feedback Signal Cards
 *
 * Displays feed-back signals from execution with "Apply" button for re-tuning.
 * Used in S&OP Policy, MRS Candidates, and Execution feedback tabs.
 */
import React, { useState, useEffect } from 'react';
import {
  Box, Paper, Typography, Button, Chip, Alert, CircularProgress,
  Card, CardContent, CardActions, Grid, Divider,
} from '@mui/material';
import {
  TrendingUp as TrendIcon,
  TrendingDown as TrendDownIcon,
  Warning as WarningIcon,
  CheckCircle as CheckIcon,
  ArrowUpward as UpIcon,
  ArrowDownward as DownIcon,
} from '@mui/icons-material';
import { getFeedbackSignals, applyFeedbackSignal } from '../../services/planningCascadeApi';

const SignalCard = ({ signal, onApply, applying }) => {
  const deviation = signal.deviation || 0;
  const isNegative = deviation < 0;
  const hasRetune = !!signal.suggested_retune;

  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent sx={{ pb: 1 }}>
        <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={1}>
          <Chip
            label={signal.signal_type}
            size="small"
            color={Math.abs(deviation) > 0.1 ? 'warning' : 'default'}
          />
          <Chip
            label={signal.measured_at_layer}
            size="small"
            variant="outlined"
          />
        </Box>

        <Typography variant="subtitle2">{signal.metric_name}</Typography>

        <Box display="flex" alignItems="baseline" gap={1} mt={1}>
          <Typography variant="h5" sx={{ fontWeight: 'bold' }}>
            {typeof signal.metric_value === 'number' ? signal.metric_value.toFixed(2) : signal.metric_value}
          </Typography>
          {signal.threshold != null && (
            <Typography variant="body2" color="text.secondary">
              target: {signal.threshold}
            </Typography>
          )}
        </Box>

        {deviation !== 0 && (
          <Box display="flex" alignItems="center" gap={0.5} mt={0.5}>
            {isNegative ? (
              <DownIcon fontSize="small" color="error" />
            ) : (
              <UpIcon fontSize="small" color="success" />
            )}
            <Typography variant="body2" color={isNegative ? 'error.main' : 'success.main'}>
              {isNegative ? '' : '+'}{(deviation * 100).toFixed(1)}% deviation
            </Typography>
          </Box>
        )}

        {signal.details && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            {typeof signal.details === 'object'
              ? Object.entries(signal.details).map(([k, v]) => `${k}: ${v}`).join(', ')
              : signal.details}
          </Typography>
        )}

        {hasRetune && (
          <Alert severity="info" sx={{ mt: 1 }} variant="outlined">
            <Typography variant="caption">
              Suggested: {signal.suggested_retune.parameter} →{' '}
              <strong>{signal.suggested_retune.suggested}</strong>{' '}
              (current: {signal.suggested_retune.current})
            </Typography>
          </Alert>
        )}
      </CardContent>

      <CardActions sx={{ px: 2, pt: 0 }}>
        <Box display="flex" gap={1} width="100%" justifyContent="space-between" alignItems="center">
          <Typography variant="caption" color="text.secondary">
            → {signal.fed_back_to}
          </Typography>
          <Box display="flex" gap={1}>
            {signal.actioned ? (
              <Chip icon={<CheckIcon />} label="Applied" size="small" color="success" variant="outlined" />
            ) : hasRetune ? (
              <Button
                size="small"
                variant="contained"
                onClick={() => onApply(signal.id)}
                disabled={applying}
              >
                Apply Re-tune
              </Button>
            ) : (
              <Chip label="Info only" size="small" variant="outlined" />
            )}
          </Box>
        </Box>
      </CardActions>
    </Card>
  );
};

const FeedbackSignalCards = ({ configId, fedBackTo = null, limit = 20 }) => {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    loadSignals();
  }, [configId, fedBackTo]);

  const loadSignals = async () => {
    try {
      setLoading(true);
      const data = await getFeedbackSignals(configId, { fedBackTo, limit });
      setSignals(data.signals || []);
    } catch (error) {
      console.error('Failed to load feedback signals', error);
    } finally {
      setLoading(false);
    }
  };

  const handleApply = async (signalId) => {
    try {
      setApplying(true);
      await applyFeedbackSignal(signalId);
      loadSignals(); // Refresh
    } catch (error) {
      console.error('Failed to apply feedback signal', error);
    } finally {
      setApplying(false);
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={4}>
        <CircularProgress />
      </Box>
    );
  }

  if (signals.length === 0) {
    return (
      <Paper variant="outlined" sx={{ p: 3, textAlign: 'center' }}>
        <Typography variant="body2" color="text.secondary">
          No feed-back signals yet. Execute commits to generate outcome data.
        </Typography>
      </Paper>
    );
  }

  // Separate actionable from info-only
  const actionable = signals.filter(s => s.suggested_retune && !s.actioned);
  const infoOnly = signals.filter(s => !s.suggested_retune || s.actioned);

  return (
    <Box>
      {actionable.length > 0 && (
        <Box mb={3}>
          <Typography variant="subtitle2" gutterBottom>
            Suggested Re-tunes ({actionable.length})
          </Typography>
          <Grid container spacing={2}>
            {actionable.map((signal) => (
              <Grid item xs={12} sm={6} md={4} key={signal.id}>
                <SignalCard signal={signal} onApply={handleApply} applying={applying} />
              </Grid>
            ))}
          </Grid>
        </Box>
      )}

      {infoOnly.length > 0 && (
        <Box>
          <Typography variant="subtitle2" gutterBottom>
            Outcome Signals ({infoOnly.length})
          </Typography>
          <Grid container spacing={2}>
            {infoOnly.map((signal) => (
              <Grid item xs={12} sm={6} md={4} key={signal.id}>
                <SignalCard signal={signal} onApply={handleApply} applying={applying} />
              </Grid>
            ))}
          </Grid>
        </Box>
      )}
    </Box>
  );
};

export default FeedbackSignalCards;
