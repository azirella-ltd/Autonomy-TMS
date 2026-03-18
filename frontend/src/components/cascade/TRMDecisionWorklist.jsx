/**
 * TRM Decision Worklist
 *
 * Shared component for all 4 TRM specialist worklists.
 * Displays a table of TRM-proposed decisions with:
 *   - Decision details (context, recommendation, confidence)
 *   - Accept / Override / Reject actions
 *   - Override reason capture (reason_code dropdown + reason_text)
 *   - Override value fields (customizable per TRM type)
 *
 * Override reasons and values are written to planning_decisions and
 * trm_replay_buffer with is_expert=True for RL training.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Button, Chip, Dialog, DialogTitle, DialogContent,
  DialogActions, TextField, MenuItem, Alert, CircularProgress, Grid,
  Card, CardContent, IconButton, Tooltip, LinearProgress,
} from '@mui/material';
import {
  CheckCircle as AcceptIcon,
  Edit as OverrideIcon,
  XCircle as RejectIcon,
  Info as InfoIcon,
  HelpCircle as WhyIcon,
  RefreshCw as RefreshIcon,
} from 'lucide-react';

// Override reason codes aligned with planning_decisions.reason_code
const REASON_CODES = [
  { value: 'MARKET_INTELLIGENCE', label: 'Market Intelligence' },
  { value: 'CUSTOMER_COMMITMENT', label: 'Customer Commitment' },
  { value: 'CAPACITY_CONSTRAINT', label: 'Capacity Constraint' },
  { value: 'SUPPLIER_ISSUE', label: 'Supplier Issue' },
  { value: 'QUALITY_CONCERN', label: 'Quality Concern' },
  { value: 'COST_OPTIMIZATION', label: 'Cost Optimization' },
  { value: 'SERVICE_LEVEL', label: 'Service Level Priority' },
  { value: 'INVENTORY_BUFFER', label: 'Inventory Buffer Adjustment' },
  { value: 'DEMAND_CHANGE', label: 'Demand Change' },
  { value: 'EXPEDITE_REQUIRED', label: 'Expedite Required' },
  { value: 'RISK_MITIGATION', label: 'Risk Mitigation' },
  { value: 'OTHER', label: 'Other (explain below)' },
];

/**
 * Confidence indicator with color coding
 */
const ConfidenceChip = ({ confidence }) => {
  if (confidence == null) return <Chip label="—" size="small" variant="outlined" />;
  const pct = (confidence * 100).toFixed(0);
  const color = confidence >= 0.9 ? 'success' : confidence >= 0.7 ? 'warning' : 'error';
  return <Chip label={`${pct}%`} size="small" color={color} variant="outlined" />;
};

/**
 * Status chip with appropriate color
 */
const StatusChip = ({ status }) => {
  // AIIO model: INFORMED / ACTIONED / INSPECTED / OVERRIDDEN
  const colorMap = {
    INFORMED: 'info',
    ACTIONED: 'success',
    INSPECTED: 'default',
    OVERRIDDEN: 'warning',
    OUTCOME_RECORDED: 'default',
  };
  return (
    <Chip
      label={status?.replace(/_/g, ' ') || 'UNKNOWN'}
      size="small"
      color={colorMap[status] || 'default'}
      variant={status === 'INFORMED' ? 'filled' : 'outlined'}
    />
  );
};

/**
 * Override Dialog — captures reason code, reason text, and override values.
 * The overrideFields prop defines TRM-specific fields the user can change.
 */
const OverrideDialog = ({ open, onClose, onSubmit, decision, overrideFields }) => {
  const [reasonCode, setReasonCode] = useState('');
  const [reasonText, setReasonText] = useState('');
  const [overrideValues, setOverrideValues] = useState({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open && decision) {
      // Pre-fill override values with current TRM recommendation
      const defaults = {};
      (overrideFields || []).forEach(f => {
        defaults[f.key] = decision[f.key] ?? f.default ?? '';
      });
      setOverrideValues(defaults);
      setReasonCode('');
      setReasonText('');
    }
  }, [open, decision, overrideFields]);

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await onSubmit({
        decision_id: decision.id,
        action: 'override',
        reason_code: reasonCode,
        reason_text: reasonText,
        override_values: overrideValues,
      });
      onClose();
    } catch (err) {
      console.error('Override failed', err);
    } finally {
      setSubmitting(false);
    }
  };

  const canSubmit = reasonCode && reasonText.trim().length > 0;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Override AI Decision</DialogTitle>
      <DialogContent>
        {decision && (
          <Box sx={{ mb: 2 }}>
            <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>
              <Typography variant="body2">
                Your override will be recorded and used to train the AI agent
                via reinforcement learning. Please provide a clear reason.
              </Typography>
            </Alert>

            {/* Override value fields (TRM-specific) */}
            {(overrideFields || []).map(field => (
              <TextField
                key={field.key}
                label={field.label}
                type={field.type || 'text'}
                value={overrideValues[field.key] ?? ''}
                onChange={(e) => setOverrideValues(prev => ({
                  ...prev,
                  [field.key]: field.type === 'number' ? Number(e.target.value) : e.target.value,
                }))}
                fullWidth
                margin="normal"
                size="small"
                helperText={field.helperText}
                select={!!field.options}
                InputProps={field.inputProps}
              >
                {field.options?.map(opt => (
                  <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
                ))}
              </TextField>
            ))}

            {/* Reason code (required) */}
            <TextField
              select
              label="Override Reason"
              value={reasonCode}
              onChange={(e) => setReasonCode(e.target.value)}
              fullWidth
              margin="normal"
              size="small"
              required
            >
              {REASON_CODES.map(rc => (
                <MenuItem key={rc.value} value={rc.value}>{rc.label}</MenuItem>
              ))}
            </TextField>

            {/* Free-text justification (required) */}
            <TextField
              label="Explanation"
              value={reasonText}
              onChange={(e) => setReasonText(e.target.value)}
              fullWidth
              margin="normal"
              size="small"
              multiline
              rows={3}
              required
              placeholder="Describe why you are overriding this decision..."
              helperText="This explanation is used to improve the AI agent"
            />
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={submitting}>Cancel</Button>
        <Button
          onClick={handleSubmit}
          variant="contained"
          color="warning"
          disabled={!canSubmit || submitting}
        >
          {submitting ? 'Submitting...' : 'Submit Override'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

/**
 * Main TRM Decision Worklist component.
 *
 * Props:
 *   configId       - Supply chain config ID
 *   trmType        - TRM type: 'atp_executor' | 'rebalancing' | 'po_creation' | 'order_tracking'
 *   title          - Page title
 *   columns        - Array of { key, label, render? } for decision-specific columns
 *   overrideFields - Array of { key, label, type, options?, helperText? } for override dialog
 *   summaryCards   - Function(decisions) returning summary card data
 *   fetchDecisions - async (configId, filters) => { decisions: [...], total }
 *   submitAction   - async (payload) => result  (accept/override/reject)
 *   canManage      - boolean, whether user can accept/override/reject
 */
const TRMDecisionWorklist = ({
  configId,
  trmType,
  title,
  columns = [],
  overrideFields = [],
  summaryCards,
  fetchDecisions,
  submitAction,
  canManage = false,
  initialStatusFilter,
}) => {
  const [decisions, setDecisions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedDecision, setSelectedDecision] = useState(null);
  const [overrideDialogOpen, setOverrideDialogOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState(null); // decision id being actioned
  const [statusFilter, setStatusFilter] = useState(initialStatusFilter || 'INFORMED');

  const loadDecisions = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchDecisions(configId, {
        trm_type: trmType,
        status: statusFilter !== 'ALL' ? statusFilter : undefined,
        limit: 50,
      });
      // Normalize: spread context fields onto each decision for column renderers
      const normalized = (data.decisions || []).map(d => ({
        ...d,
        ...(d.context || {}),
        timestamp: d.timestamp || d.created_at,
      }));
      setDecisions(normalized);
    } catch (err) {
      console.error('Failed to load decisions', err);
    } finally {
      setLoading(false);
    }
  }, [configId, trmType, statusFilter, fetchDecisions]);

  useEffect(() => {
    if (configId) loadDecisions();
  }, [configId, loadDecisions]);

  const handleAccept = async (decision) => {
    setActionLoading(decision.id);
    try {
      await submitAction({
        decision_id: decision.id,
        action: 'accept',
      });
      loadDecisions();
    } catch (err) {
      console.error('Accept failed', err);
    } finally {
      setActionLoading(null);
    }
  };

  const handleInspect = async (decision) => {
    setActionLoading(decision.id);
    try {
      await submitAction({
        decision_id: decision.id,
        action: 'inspect',
      });
      loadDecisions();
    } catch (err) {
      console.error('Inspect failed', err);
    } finally {
      setActionLoading(null);
    }
  };

  const openOverride = (decision) => {
    setSelectedDecision(decision);
    setOverrideDialogOpen(true);
  };

  const handleOverrideSubmit = async (payload) => {
    await submitAction(payload);
    loadDecisions();
  };

  // Summary cards
  const cards = summaryCards ? summaryCards(decisions) : [];
  const pendingCount = decisions.filter(d => d.status === 'INFORMED').length;

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={6}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      {/* Summary Cards */}
      {cards.length > 0 && (
        <Grid container spacing={2} sx={{ mb: 3 }}>
          {cards.map((card, i) => (
            <Grid item xs={6} sm={4} md={3} lg={2} key={i}>
              <Card variant="outlined">
                <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                  <Typography variant="caption" color="text.secondary">{card.title}</Typography>
                  <Typography variant="h5" sx={{ fontWeight: 'bold', color: card.color || '#1976d2' }}>
                    {card.value}
                  </Typography>
                  {card.subtitle && (
                    <Typography variant="caption" color="text.secondary">{card.subtitle}</Typography>
                  )}
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      {/* Filter bar */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Box display="flex" gap={1}>
          {['INFORMED', 'ACTIONED', 'INSPECTED', 'OVERRIDDEN', 'ALL'].map(status => (
            <Chip
              key={status}
              label={status === 'INFORMED' ? `Informed (${pendingCount})` : status}
              onClick={() => setStatusFilter(status)}
              color={statusFilter === status ? 'primary' : 'default'}
              variant={statusFilter === status ? 'filled' : 'outlined'}
              size="small"
            />
          ))}
        </Box>
        <Tooltip title="Refresh decisions">
          <IconButton onClick={loadDecisions} size="small">
            <RefreshIcon size={18} />
          </IconButton>
        </Tooltip>
      </Box>

      {/* Decision Table */}
      {decisions.length === 0 ? (
        <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="body2" color="text.secondary">
            No {statusFilter === 'ALL' ? '' : statusFilter.toLowerCase()} decisions found for this configuration.
          </Typography>
        </Paper>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: 'grey.50' }}>
                <TableCell>Time</TableCell>
                {columns.map(col => (
                  <TableCell key={col.key}>{col.label}</TableCell>
                ))}
                <TableCell>Confidence</TableCell>
                <TableCell>Status</TableCell>
                {canManage && <TableCell align="right">Actions</TableCell>}
              </TableRow>
            </TableHead>
            <TableBody>
              {decisions.map(decision => (
                <TableRow
                  key={decision.id}
                  hover
                  sx={{
                    bgcolor: decision.status === 'INFORMED' ? 'action.hover' : undefined,
                    opacity: decision.status === 'OUTCOME_RECORDED' ? 0.7 : 1,
                  }}
                >
                  <TableCell>
                    <Typography variant="caption">
                      {decision.timestamp
                        ? new Date(decision.timestamp).toLocaleString([], {
                            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                          })
                        : '—'}
                    </Typography>
                  </TableCell>
                  {columns.map(col => (
                    <TableCell key={col.key}>
                      {col.render ? col.render(decision) : (decision[col.key] ?? '—')}
                    </TableCell>
                  ))}
                  <TableCell>
                    <ConfidenceChip confidence={decision.confidence} />
                  </TableCell>
                  <TableCell>
                    <StatusChip status={decision.status} />
                  </TableCell>
                  {canManage && (
                    <TableCell align="right">
                      {decision.status === 'INFORMED' && (
                        <Box display="flex" gap={0.5} justifyContent="flex-end">
                          <Tooltip title="Accept AI decision">
                            <IconButton
                              size="small"
                              color="success"
                              onClick={() => handleAccept(decision)}
                              disabled={actionLoading === decision.id}
                            >
                              <AcceptIcon size={16} />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="Mark as reviewed — no action needed">
                            <IconButton
                              size="small"
                              color="info"
                              onClick={() => handleInspect(decision)}
                              disabled={actionLoading === decision.id}
                            >
                              <WhyIcon size={16} />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="Override with reason">
                            <IconButton
                              size="small"
                              color="warning"
                              onClick={() => openOverride(decision)}
                              disabled={actionLoading === decision.id}
                            >
                              <OverrideIcon size={16} />
                            </IconButton>
                          </Tooltip>
                        </Box>
                      )}
                      {decision.status === 'OVERRIDDEN' && decision.reason_code && (
                        <Tooltip title={`${decision.reason_code}: ${decision.reason_text || ''}`}>
                          <IconButton size="small">
                            <InfoIcon size={16} />
                          </IconButton>
                        </Tooltip>
                      )}
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* Override Dialog */}
      <OverrideDialog
        open={overrideDialogOpen}
        onClose={() => setOverrideDialogOpen(false)}
        onSubmit={handleOverrideSubmit}
        decision={selectedDecision}
        overrideFields={overrideFields}
      />
    </Box>
  );
};

export default TRMDecisionWorklist;
