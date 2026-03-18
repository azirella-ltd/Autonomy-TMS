/**
 * BSC Configuration Page
 *
 * Tenant-admin page for configuring the Balanced Scorecard weights used by
 * the CDT (Conformal Decision Theory) simulation calibration service.
 *
 * Phase 1 — two active cost components, both to be MINIMISED:
 *   • Inventory holding cost  (carrying excess stock = money tied up)
 *   • Backlog / stockout cost (unfulfilled demand = lost revenue + penalties)
 *
 * Weights determine each component's relative importance in calibrating the
 * risk bounds across all 11 TRM agents. They must sum to 1.0.
 *
 * Future phases will unlock customer-service, operational, and strategic
 * pillars once the corresponding metrics are wired up.
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
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import api from '../../services/api';

// ── Default weights (Phase 1) ─────────────────────────────────────────────
const DEFAULTS = { holding_cost_weight: 0.5, backlog_cost_weight: 0.5, autonomy_threshold: 0.5, urgency_threshold: 0.65, likelihood_threshold: 0.70, benefit_threshold: 0 };
const WEIGHT_PRECISION = 2;

// ── Helper: format weight as percentage label ─────────────────────────────
const pct = (v) => `${Math.round(v * 100)}%`;

// ── WeightSlider ─────────────────────────────────────────────────────────
/**
 * A labelled slider for one BSC weight.
 * Changing this slider adjusts the other to keep the sum at 1.0.
 */
function WeightSlider({ label, description, value, onChange, color }) {
  const handleChange = (_event, newValue) => {
    onChange(newValue / 100);
  };

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1} mb={0.5}>
        <TrendingDownIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
        <Typography variant="body2" fontWeight={600}>
          {label}
        </Typography>
        <Chip
          label={pct(value)}
          size="small"
          sx={{ fontWeight: 700, bgcolor: color, color: '#fff', minWidth: 52 }}
        />
        <Tooltip title={description} placement="right">
          <InfoOutlinedIcon sx={{ fontSize: 14, color: 'text.disabled', cursor: 'help' }} />
        </Tooltip>
      </Stack>
      <Slider
        value={Math.round(value * 100)}
        min={0}
        max={100}
        step={1}
        onChange={handleChange}
        sx={{ color }}
        valueLabelDisplay="auto"
        valueLabelFormat={(v) => `${v}%`}
      />
      <Typography variant="caption" color="text.secondary">
        {description}
      </Typography>
    </Box>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────
export default function BscConfigPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [weights, setWeights] = useState(DEFAULTS);
  const [notes, setNotes] = useState('');
  const [savedBy, setSavedBy] = useState(null);
  const [savedAt, setSavedAt] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [toast, setToast] = useState({ open: false, message: '', severity: 'success' });

  // ── Load ────────────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/bsc-config');
      setWeights({
        holding_cost_weight: data.holding_cost_weight,
        backlog_cost_weight: data.backlog_cost_weight,
        autonomy_threshold: data.autonomy_threshold ?? 0.5,
        urgency_threshold: data.urgency_threshold ?? 0.65,
        likelihood_threshold: data.likelihood_threshold ?? 0.70,
        benefit_threshold: data.benefit_threshold ?? 0,
      });
      setNotes(data.notes || '');
      setSavedBy(data.updated_by_name);
      setSavedAt(data.updated_at ? new Date(data.updated_at).toLocaleString() : null);
      setDirty(false);
    } catch (err) {
      showToast('Failed to load BSC configuration', 'error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // ── Slider change — adjust counterpart to maintain sum = 1.0 ───────────
  const handleHoldingChange = (newHolding) => {
    const clamped = Math.min(1.0, Math.max(0.0, newHolding));
    setWeights({ holding_cost_weight: clamped, backlog_cost_weight: 1.0 - clamped });
    setDirty(true);
  };

  const handleBacklogChange = (newBacklog) => {
    const clamped = Math.min(1.0, Math.max(0.0, newBacklog));
    setWeights({ holding_cost_weight: 1.0 - clamped, backlog_cost_weight: clamped });
    setDirty(true);
  };

  const handleReset = () => {
    setWeights(DEFAULTS);
    setDirty(true);
  };

  // ── Save ────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    const total = weights.holding_cost_weight + weights.backlog_cost_weight;
    if (Math.abs(total - 1.0) > 0.001) {
      showToast('Weights must sum to 100%', 'error');
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.put('/bsc-config', {
        holding_cost_weight: parseFloat(weights.holding_cost_weight.toFixed(WEIGHT_PRECISION)),
        backlog_cost_weight: parseFloat(weights.backlog_cost_weight.toFixed(WEIGHT_PRECISION)),
        customer_weight: 0.0,
        operational_weight: 0.0,
        strategic_weight: 0.0,
        autonomy_threshold: parseFloat(weights.autonomy_threshold.toFixed(WEIGHT_PRECISION)),
        urgency_threshold: parseFloat(weights.urgency_threshold.toFixed(WEIGHT_PRECISION)),
        likelihood_threshold: parseFloat(weights.likelihood_threshold.toFixed(WEIGHT_PRECISION)),
        benefit_threshold: weights.benefit_threshold ?? 0,
        notes: notes || null,
      });
      setSavedBy(data.updated_by_name);
      setSavedAt(new Date(data.updated_at).toLocaleString());
      setDirty(false);
      showToast('BSC configuration saved', 'success');
    } catch (err) {
      const detail = err?.response?.data?.detail || 'Save failed';
      showToast(typeof detail === 'string' ? detail : JSON.stringify(detail), 'error');
    } finally {
      setSaving(false);
    }
  };

  const showToast = (message, severity) =>
    setToast({ open: true, message, severity });

  // ── Render ───────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight={300}>
        <CircularProgress />
      </Box>
    );
  }

  const sumOk = Math.abs(weights.holding_cost_weight + weights.backlog_cost_weight - 1.0) < 0.001;

  return (
    <Box maxWidth={720} mx="auto" p={3}>
      {/* ── Header ────────────────────────────────────────────────────── */}
      <Typography variant="h5" fontWeight={700} gutterBottom>
        Balanced Scorecard Configuration
      </Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        These weights control how the digital twin simulation calibrates the risk
        bounds (CDT) for all 11 TRM agents. Both cost components are{' '}
        <strong>to be minimised</strong> — the weights set their relative importance
        in the calibration loss function.
      </Typography>

      {/* ── Phase badge ───────────────────────────────────────────────── */}
      <Stack direction="row" spacing={1} mb={3}>
        <Chip label="Phase 1 — Active" color="success" size="small" />
        <Chip label="Phase 2: Customer Service — Coming soon" size="small" variant="outlined" />
        <Chip label="Phase 2: Operational — Coming soon" size="small" variant="outlined" />
      </Stack>

      {/* ── Weight sliders ────────────────────────────────────────────── */}
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={2}>
            Cost Weights
          </Typography>
          <Alert severity="info" sx={{ mb: 3, fontSize: 13 }}>
            Both costs are negative outcomes — the system learns to minimise them.
            Increasing a weight makes the corresponding cost more influential when
            calibrating TRM confidence bounds. Weights always sum to 100%.
          </Alert>

          <Stack spacing={4}>
            <WeightSlider
              label="Inventory Holding Cost"
              description="Cost of carrying excess stock: capital tied up, warehousing, obsolescence, insurance."
              value={weights.holding_cost_weight}
              onChange={handleHoldingChange}
              color="#1976d2"
            />
            <WeightSlider
              label="Backlog / Stockout Cost"
              description="Cost of unfulfilled demand: lost revenue, expediting fees, customer penalties, lost goodwill."
              value={weights.backlog_cost_weight}
              onChange={handleBacklogChange}
              color="#d32f2f"
            />
          </Stack>

          <Divider sx={{ my: 3 }} />

          {/* Sum indicator */}
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="body2" color="text.secondary">
              Total weight
            </Typography>
            <Chip
              label={`${Math.round((weights.holding_cost_weight + weights.backlog_cost_weight) * 100)}%`}
              color={sumOk ? 'success' : 'error'}
              size="small"
              sx={{ fontWeight: 700 }}
            />
          </Stack>
          {!sumOk && (
            <Typography variant="caption" color="error" mt={0.5} display="block">
              Weights must sum to exactly 100%.
            </Typography>
          )}

          {/* Visual split bar */}
          <Box mt={2}>
            <Box
              sx={{
                height: 12,
                borderRadius: 6,
                overflow: 'hidden',
                display: 'flex',
                bgcolor: 'grey.200',
              }}
            >
              <Box
                sx={{
                  width: `${weights.holding_cost_weight * 100}%`,
                  bgcolor: '#1976d2',
                  transition: 'width 0.2s ease',
                }}
              />
              <Box
                sx={{
                  width: `${weights.backlog_cost_weight * 100}%`,
                  bgcolor: '#d32f2f',
                  transition: 'width 0.2s ease',
                }}
              />
            </Box>
            <Stack direction="row" justifyContent="space-between" mt={0.5}>
              <Typography variant="caption" color="#1976d2" fontWeight={600}>
                Holding {pct(weights.holding_cost_weight)}
              </Typography>
              <Typography variant="caption" color="#d32f2f" fontWeight={600}>
                Backlog {pct(weights.backlog_cost_weight)}
              </Typography>
            </Stack>
          </Box>
        </CardContent>
      </Card>

      {/* ── Agent Autonomy ────────────────────────────────────────────── */}
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>
            Agent Autonomy Thresholds
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
                label={pct(weights.urgency_threshold)}
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
                value={Math.round(weights.urgency_threshold * 100)}
                min={0} max={100} step={5}
                onChange={(_e, v) => {
                  setWeights(prev => ({ ...prev, urgency_threshold: v / 100 }));
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
          <Box>
            <Stack direction="row" alignItems="center" spacing={1} mb={0.5}>
              <Typography variant="body2" fontWeight={600}>Agent Confidence Threshold</Typography>
              <Chip
                label={pct(weights.likelihood_threshold)}
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
                value={Math.round(weights.likelihood_threshold * 100)}
                min={0} max={100} step={5}
                onChange={(_e, v) => {
                  setWeights(prev => ({ ...prev, likelihood_threshold: v / 100 }));
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
                label={weights.benefit_threshold > 0 ? `$${weights.benefit_threshold.toLocaleString()}` : 'Off'}
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
                value={weights.benefit_threshold}
                min={0} max={10000} step={100}
                onChange={(_e, v) => {
                  setWeights(prev => ({ ...prev, benefit_threshold: v }));
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

      {/* ── Notes ────────────────────────────────────────────────────── */}
      <TextField
        label="Notes (optional)"
        placeholder="e.g. Adjusted for Q2 peak season — backlog cost elevated due to service agreements."
        multiline
        rows={2}
        fullWidth
        value={notes}
        onChange={(e) => { setNotes(e.target.value); setDirty(true); }}
        inputProps={{ maxLength: 500 }}
        sx={{ mb: 3 }}
        helperText={`${notes.length}/500`}
      />

      {/* ── Action buttons ───────────────────────────────────────────── */}
      <Stack direction="row" spacing={2} alignItems="center">
        <Button
          variant="contained"
          startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <SaveOutlinedIcon />}
          onClick={handleSave}
          disabled={saving || !dirty || !sumOk}
        >
          {saving ? 'Saving…' : 'Save Configuration'}
        </Button>
        <Button
          variant="outlined"
          startIcon={<RestoreOutlinedIcon />}
          onClick={handleReset}
          disabled={saving}
        >
          Reset to Equal (50 / 50)
        </Button>
      </Stack>

      {/* ── Last saved info ──────────────────────────────────────────── */}
      {savedAt && (
        <Typography variant="caption" color="text.disabled" mt={2} display="block">
          Last saved {savedAt}{savedBy ? ` by ${savedBy}` : ''}
        </Typography>
      )}

      {/* ── Future pillars notice ─────────────────────────────────────── */}
      <Card variant="outlined" sx={{ mt: 4, bgcolor: 'grey.50' }}>
        <CardContent>
          <Typography variant="subtitle2" fontWeight={700} color="text.secondary" gutterBottom>
            Coming in Phase 2: Full Balanced Scorecard
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Additional pillars will be unlocked once their metrics are available:
          </Typography>
          <Stack direction="row" spacing={1} mt={1.5} flexWrap="wrap" useFlexGap>
            {[
              { label: 'Customer Service', desc: 'Fill rate, OTIF, order satisfaction' },
              { label: 'Operational', desc: 'Inventory turns, days of supply' },
              { label: 'Strategic', desc: 'Network resilience, bullwhip ratio' },
            ].map(({ label, desc }) => (
              <Tooltip key={label} title={desc} placement="top">
                <Chip
                  label={label}
                  size="small"
                  variant="outlined"
                  sx={{ opacity: 0.55, cursor: 'default' }}
                />
              </Tooltip>
            ))}
          </Stack>
        </CardContent>
      </Card>

      {/* ── Toast ────────────────────────────────────────────────────── */}
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
