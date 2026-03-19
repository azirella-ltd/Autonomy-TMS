/**
 * Tenant Settings Page
 *
 * Tenant-admin page for configuring display preferences and decision thresholds
 * that govern agent autonomy across all 11 TRM agents.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  FormControlLabel,
  Radio,
  RadioGroup,
  Slider,
  Snackbar,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import SaveOutlinedIcon from '@mui/icons-material/SaveOutlined';
import RestoreOutlinedIcon from '@mui/icons-material/RestoreOutlined';
import api from '../../services/api';

// ── Defaults ─────────────────────────────────────────────────────────────────
const DEFAULTS = {
  urgency_threshold: 0.65,
  likelihood_threshold: 0.70,
  benefit_threshold: 0,
  display_identifiers: 'name',
};

// ── Helper: format as percentage label ───────────────────────────────────────
const pct = (v) => `${Math.round(v * 100)}%`;

// ── Main page ────────────────────────────────────────────────────────────────
export default function BscConfigPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState(DEFAULTS);
  const [notes, setNotes] = useState('');
  const [savedBy, setSavedBy] = useState(null);
  const [savedAt, setSavedAt] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [toast, setToast] = useState({ open: false, message: '', severity: 'success' });

  // ── Load ──────────────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/bsc-config');
      setConfig({
        urgency_threshold: data.urgency_threshold ?? 0.65,
        likelihood_threshold: data.likelihood_threshold ?? 0.70,
        benefit_threshold: data.benefit_threshold ?? 0,
        display_identifiers: data.display_identifiers || 'name',
      });
      setNotes(data.notes || '');
      setSavedBy(data.updated_by_name);
      setSavedAt(data.updated_at ? new Date(data.updated_at).toLocaleString() : null);
      setDirty(false);
    } catch (err) {
      showToast('Failed to load tenant settings', 'error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // ── Reset to defaults ─────────────────────────────────────────────────────
  const handleReset = () => {
    setConfig(DEFAULTS);
    setDirty(true);
  };

  // ── Save ──────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    setSaving(true);
    try {
      const { data } = await api.put('/bsc-config', {
        urgency_threshold: parseFloat(config.urgency_threshold.toFixed(2)),
        likelihood_threshold: parseFloat(config.likelihood_threshold.toFixed(2)),
        benefit_threshold: config.benefit_threshold ?? 0,
        display_identifiers: config.display_identifiers,
        notes: notes || null,
      });
      setSavedBy(data.updated_by_name);
      setSavedAt(new Date(data.updated_at).toLocaleString());
      setDirty(false);
      showToast('Tenant settings saved', 'success');
    } catch (err) {
      const detail = err?.response?.data?.detail || 'Save failed';
      showToast(typeof detail === 'string' ? detail : JSON.stringify(detail), 'error');
    } finally {
      setSaving(false);
    }
  };

  const showToast = (message, severity) =>
    setToast({ open: true, message, severity });

  // ── Render ────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight={300}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box maxWidth={720} mx="auto" p={3}>
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <Typography variant="h5" fontWeight={700} gutterBottom>
        Tenant Settings
      </Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Configure display preferences and decision thresholds that govern when
        agents act autonomously vs. surface decisions for human review.
      </Typography>

      {/* ── Display Preferences ─────────────────────────────────────────── */}
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>
            Display Preferences
          </Typography>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Choose how entities (sites, products, lanes) are identified throughout
            the application.
          </Typography>
          <RadioGroup
            row
            value={config.display_identifiers}
            onChange={(e) => {
              setConfig((prev) => ({ ...prev, display_identifiers: e.target.value }));
              setDirty(true);
            }}
          >
            <FormControlLabel
              value="name"
              control={<Radio />}
              label="Show Names"
            />
            <FormControlLabel
              value="id"
              control={<Radio />}
              label="Show IDs"
            />
          </RadioGroup>
        </CardContent>
      </Card>

      {/* ── Decision Thresholds ─────────────────────────────────────────── */}
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>
            Decision Thresholds
          </Typography>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Three dimensions control when agents act autonomously vs. surface decisions
            for human review: <strong>Urgency</strong> (cost of inaction &times; time pressure),{' '}
            <strong>Likelihood</strong> (agent confidence), and <strong>Benefit</strong> (net
            economic gain from the recommended action).
          </Typography>

          <Alert severity="info" sx={{ mb: 3, fontSize: 13 }}>
            <strong>High urgency + uncertain</strong> &rarr; Always surfaced (loss prevention)<br />
            <strong>Routine + confident</strong> &rarr; Auto-actioned (agent handles it)<br />
            <strong>Routine + uncertain</strong> &rarr; Surfaced for human validation<br />
            <br />
            <em>Based on Kahneman &amp; Tversky&apos;s Prospect Theory (1979): losses loom ~2&times;
            larger than equivalent gains. The queue prioritises loss-prevention (urgency)
            above gain-capture (benefit) at equal dollar values.</em>
          </Alert>

          {/* Urgency threshold */}
          <Box mb={3}>
            <Stack direction="row" alignItems="center" spacing={1} mb={0.5}>
              <Typography variant="body2" fontWeight={600}>Urgency Threshold</Typography>
              <Chip
                label={pct(config.urgency_threshold)}
                size="small"
                sx={{ fontWeight: 700, bgcolor: '#dc2626', color: '#fff', minWidth: 52 }}
              />
              <Tooltip title="Decisions at or above this urgency are ALWAYS surfaced for human review, regardless of agent confidence." placement="right">
                <InfoOutlinedIcon sx={{ fontSize: 14, color: 'text.disabled', cursor: 'help' }} />
              </Tooltip>
            </Stack>
            <Typography variant="caption" color="text.secondary" display="block" mb={1}>
              How urgent must a decision be before you want to see it?
            </Typography>
            <Stack direction="row" alignItems="center" spacing={2}>
              <Typography variant="caption" color="text.secondary" sx={{ minWidth: 80 }}>
                Surface more
              </Typography>
              <Slider
                value={Math.round(config.urgency_threshold * 100)}
                min={0} max={100} step={5}
                onChange={(_e, v) => {
                  setConfig((prev) => ({ ...prev, urgency_threshold: v / 100 }));
                  setDirty(true);
                }}
                sx={{ color: '#dc2626' }}
                valueLabelDisplay="auto"
                valueLabelFormat={(v) => `${v}%`}
                marks={[
                  { value: 20, label: 'Low' },
                  { value: 40, label: 'Medium' },
                  { value: 65, label: 'High' },
                  { value: 85, label: 'Critical' },
                ]}
              />
              <Typography variant="caption" color="text.secondary" sx={{ minWidth: 80, textAlign: 'right' }}>
                Only critical
              </Typography>
            </Stack>
          </Box>

          <Divider sx={{ mb: 3 }} />

          {/* Likelihood threshold */}
          <Box mb={3}>
            <Stack direction="row" alignItems="center" spacing={1} mb={0.5}>
              <Typography variant="body2" fontWeight={600}>Agent Confidence Threshold</Typography>
              <Chip
                label={pct(config.likelihood_threshold)}
                size="small"
                sx={{ fontWeight: 700, bgcolor: '#7c3aed', color: '#fff', minWidth: 52 }}
              />
              <Tooltip title="For routine (non-urgent) decisions, the agent must be at least this confident to act alone. Below this, the decision is surfaced for human validation." placement="right">
                <InfoOutlinedIcon sx={{ fontSize: 14, color: 'text.disabled', cursor: 'help' }} />
              </Tooltip>
            </Stack>
            <Typography variant="caption" color="text.secondary" display="block" mb={1}>
              How confident must the agent be to act without your review?
            </Typography>
            <Stack direction="row" alignItems="center" spacing={2}>
              <Typography variant="caption" color="text.secondary" sx={{ minWidth: 80 }}>
                Trust less
              </Typography>
              <Slider
                value={Math.round(config.likelihood_threshold * 100)}
                min={0} max={100} step={5}
                onChange={(_e, v) => {
                  setConfig((prev) => ({ ...prev, likelihood_threshold: v / 100 }));
                  setDirty(true);
                }}
                sx={{ color: '#7c3aed' }}
                valueLabelDisplay="auto"
                valueLabelFormat={(v) => `${v}%`}
                marks={[
                  { value: 20, label: 'Unlikely' },
                  { value: 40, label: 'Possible' },
                  { value: 65, label: 'Likely' },
                  { value: 85, label: 'Certain' },
                ]}
              />
              <Typography variant="caption" color="text.secondary" sx={{ minWidth: 80, textAlign: 'right' }}>
                Trust more
              </Typography>
            </Stack>
          </Box>

          <Divider sx={{ mb: 3 }} />

          {/* Benefit threshold */}
          <Box>
            <Stack direction="row" alignItems="center" spacing={1} mb={0.5}>
              <Typography variant="body2" fontWeight={600}>Minimum Benefit to Auto-Action</Typography>
              <Chip
                label={config.benefit_threshold > 0 ? `$${config.benefit_threshold.toLocaleString()}` : 'Off'}
                size="small"
                sx={{ fontWeight: 700, bgcolor: '#16a34a', color: '#fff', minWidth: 52 }}
              />
              <Tooltip title="When set above $0, decisions with expected economic benefit below this amount are surfaced for awareness even when the agent is confident. Set to $0 to disable (benefit does not gate auto-action)." placement="right">
                <InfoOutlinedIcon sx={{ fontSize: 14, color: 'text.disabled', cursor: 'help' }} />
              </Tooltip>
            </Stack>
            <Typography variant="caption" color="text.secondary" display="block" mb={1}>
              Below what dollar value should decisions still be reviewed? ($0 = disabled)
            </Typography>
            <Stack direction="row" alignItems="center" spacing={2}>
              <Typography variant="caption" color="text.secondary" sx={{ minWidth: 80 }}>
                Disabled
              </Typography>
              <Slider
                value={config.benefit_threshold}
                min={0} max={10000} step={100}
                onChange={(_e, v) => {
                  setConfig((prev) => ({ ...prev, benefit_threshold: v }));
                  setDirty(true);
                }}
                sx={{ color: '#16a34a' }}
                valueLabelDisplay="auto"
                valueLabelFormat={(v) => v === 0 ? 'Off' : `$${v.toLocaleString()}`}
                marks={[
                  { value: 0, label: 'Off' },
                  { value: 1000, label: '$1K' },
                  { value: 5000, label: '$5K' },
                  { value: 10000, label: '$10K' },
                ]}
              />
              <Typography variant="caption" color="text.secondary" sx={{ minWidth: 80, textAlign: 'right' }}>
                Review more
              </Typography>
            </Stack>
          </Box>
        </CardContent>
      </Card>

      {/* ── Notes ──────────────────────────────────────────────────────── */}
      <TextField
        label="Notes (optional)"
        placeholder="e.g. Adjusted thresholds for Q2 peak season."
        multiline
        rows={2}
        fullWidth
        value={notes}
        onChange={(e) => { setNotes(e.target.value); setDirty(true); }}
        inputProps={{ maxLength: 500 }}
        sx={{ mb: 3 }}
        helperText={`${notes.length}/500`}
      />

      {/* ── Action buttons ─────────────────────────────────────────────── */}
      <Stack direction="row" spacing={2} alignItems="center">
        <Button
          variant="contained"
          startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <SaveOutlinedIcon />}
          onClick={handleSave}
          disabled={saving || !dirty}
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </Button>
        <Button
          variant="outlined"
          startIcon={<RestoreOutlinedIcon />}
          onClick={handleReset}
          disabled={saving}
        >
          Reset to Defaults
        </Button>
      </Stack>

      {/* ── Last saved info ────────────────────────────────────────────── */}
      {savedAt && (
        <Typography variant="caption" color="text.disabled" mt={2} display="block">
          Last saved {savedAt}{savedBy ? ` by ${savedBy}` : ''}
        </Typography>
      )}

      {/* ── Toast ──────────────────────────────────────────────────────── */}
      <Snackbar
        open={toast.open}
        autoHideDuration={4000}
        onClose={() => setToast((t) => ({ ...t, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          onClose={() => setToast((t) => ({ ...t, open: false }))}
          severity={toast.severity}
          sx={{ width: '100%' }}
        >
          {toast.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
