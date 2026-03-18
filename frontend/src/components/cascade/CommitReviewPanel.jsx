/**
 * Commit Review Panel
 *
 * Shared Accept/Override/Reject panel for Supply Commits and Allocation Commits.
 * Implements the Worklist pattern from the AI-as-Labor strategy.
 */
import React, { useState } from 'react';
import {
  Box, Paper, Typography, Button, TextField, MenuItem, Alert, Chip,
  Dialog, DialogTitle, DialogContent, DialogActions, Divider,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
} from '@mui/material';
import {
  CheckCircle as AcceptIcon,
  Edit as OverrideIcon,
  Cancel as RejectIcon,
  Send as SubmitIcon,
} from '@mui/icons-material';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';

const OVERRIDE_REASONS = [
  { value: 'business_knowledge', label: 'Business knowledge not captured by model' },
  { value: 'customer_priority', label: 'Customer priority change' },
  { value: 'supplier_issue', label: 'Known supplier issue' },
  { value: 'seasonal_factor', label: 'Seasonal factor not modeled' },
  { value: 'cost_constraint', label: 'Budget or cost constraint' },
  { value: 'quality_concern', label: 'Quality or compliance concern' },
  { value: 'other', label: 'Other (specify below)' },
];

const CommitReviewPanel = ({
  commit,
  commitType = 'supply',
  onAccept,
  onOverride,
  onReject,
  onSubmit,
  loading = false,
}) => {
  const { formatSupplier, formatSite } = useDisplayPreferences();
  const [overrideDialogOpen, setOverrideDialogOpen] = useState(false);
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [overrideReason, setOverrideReason] = useState('');
  const [overrideNotes, setOverrideNotes] = useState('');
  const [rejectReason, setRejectReason] = useState('');

  if (!commit) return null;

  const isProposed = commit.status === 'proposed';
  const isReviewed = commit.status === 'reviewed' || commit.status === 'accepted' || commit.status === 'overridden';
  const isSubmitted = commit.status === 'submitted' || commit.status === 'auto_submitted';

  const handleAccept = () => {
    onAccept?.(commit.id);
  };

  const handleOverrideConfirm = () => {
    onOverride?.(commit.id, {
      reason: overrideReason,
      notes: overrideNotes,
    });
    setOverrideDialogOpen(false);
    setOverrideReason('');
    setOverrideNotes('');
  };

  const handleRejectConfirm = () => {
    onReject?.(commit.id, rejectReason);
    setRejectDialogOpen(false);
    setRejectReason('');
  };

  const handleSubmit = () => {
    onSubmit?.(commit.id);
  };

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      {/* Status Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Box display="flex" alignItems="center" gap={1}>
          <Typography variant="subtitle1">
            {commitType === 'supply' ? 'Supply' : 'Allocation'} Commit #{commit.hash?.slice(0, 8)}
          </Typography>
          <Chip
            label={commit.status?.toUpperCase()}
            size="small"
            color={
              isSubmitted ? 'success' :
              commit.status === 'overridden' ? 'warning' :
              commit.status === 'rejected' ? 'error' :
              commit.status === 'accepted' ? 'info' : 'default'
            }
          />
        </Box>
        {commit.agent_confidence != null && (
          <Chip
            label={`Confidence: ${(commit.agent_confidence * 100).toFixed(0)}%`}
            size="small"
            variant="outlined"
            color={commit.agent_confidence > 0.8 ? 'success' : commit.agent_confidence > 0.5 ? 'warning' : 'error'}
          />
        )}
      </Box>

      {/* Integrity Violations */}
      {commit.integrity_violations?.length > 0 && (
        <Alert severity="error" sx={{ mb: 2 }}>
          <Typography variant="subtitle2">
            {commit.integrity_violations.length} Integrity Violation{commit.integrity_violations.length > 1 ? 's' : ''} (Blocks Submission)
          </Typography>
          {commit.integrity_violations.map((v, i) => (
            <Typography key={i} variant="body2">
              {v.type}: {v.detail || v.sku}
            </Typography>
          ))}
        </Alert>
      )}

      {/* Risk Flags */}
      {commit.risk_flags?.length > 0 && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          <Typography variant="subtitle2">
            {commit.risk_flags.length} Risk Flag{commit.risk_flags.length > 1 ? 's' : ''}
          </Typography>
          {commit.risk_flags.map((r, i) => (
            <Typography key={i} variant="body2">
              {r.type}: {r.detail}
            </Typography>
          ))}
        </Alert>
      )}

      {/* Agent Reasoning */}
      {commit.agent_reasoning && (
        <Box mb={2}>
          <Typography variant="subtitle2" gutterBottom>Agent Reasoning</Typography>
          <Typography variant="body2" color="text.secondary">
            {commit.agent_reasoning}
          </Typography>
        </Box>
      )}

      {/* Recommendations Preview */}
      {commit.recommendations?.length > 0 && (
        <Box mb={2}>
          <Typography variant="subtitle2" gutterBottom>
            Recommendations ({commit.recommendations.length} orders)
          </Typography>
          <TableContainer sx={{ maxHeight: 200 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell>SKU</TableCell>
                  <TableCell>Supplier</TableCell>
                  <TableCell>Destination</TableCell>
                  <TableCell align="right">Qty</TableCell>
                  <TableCell>Order Date</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {commit.recommendations.slice(0, 10).map((rec, i) => (
                  <TableRow key={i}>
                    <TableCell>{rec.sku}</TableCell>
                    <TableCell>{formatSupplier(rec.supplier_id, rec.supplier_name)}</TableCell>
                    <TableCell>{formatSite(rec.destination_id, rec.destination_name)}</TableCell>
                    <TableCell align="right">{rec.order_qty}</TableCell>
                    <TableCell>{rec.order_date}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          {commit.recommendations.length > 10 && (
            <Typography variant="caption" color="text.secondary">
              Showing 10 of {commit.recommendations.length} orders
            </Typography>
          )}
        </Box>
      )}

      {/* Projected Outcomes */}
      {(commit.projected_otif != null || commit.projected_inventory_cost != null) && (
        <Box display="flex" gap={2} mb={2}>
          {commit.projected_otif != null && (
            <Chip label={`OTIF: ${(commit.projected_otif * 100).toFixed(1)}%`} size="small" variant="outlined" />
          )}
          {commit.projected_inventory_cost != null && (
            <Chip label={`Cost: $${commit.projected_inventory_cost.toLocaleString()}`} size="small" variant="outlined" />
          )}
          {commit.projected_dos != null && (
            <Chip label={`DOS: ${commit.projected_dos.toFixed(1)}`} size="small" variant="outlined" />
          )}
        </Box>
      )}

      <Divider sx={{ my: 2 }} />

      {/* Action Buttons */}
      <Box display="flex" gap={1} justifyContent="flex-end">
        {isProposed && (
          <>
            <Button
              variant="outlined"
              color="error"
              startIcon={<RejectIcon />}
              onClick={() => setRejectDialogOpen(true)}
              disabled={loading}
              size="small"
            >
              Reject
            </Button>
            <Button
              variant="outlined"
              color="warning"
              startIcon={<OverrideIcon />}
              onClick={() => setOverrideDialogOpen(true)}
              disabled={loading}
              size="small"
            >
              Override
            </Button>
            <Button
              variant="contained"
              color="primary"
              startIcon={<AcceptIcon />}
              onClick={handleAccept}
              disabled={loading}
              size="small"
            >
              Accept
            </Button>
          </>
        )}
        {isReviewed && !isSubmitted && (
          <Button
            variant="contained"
            color="success"
            startIcon={<SubmitIcon />}
            onClick={handleSubmit}
            disabled={loading || (commit.integrity_violations?.length > 0)}
            size="small"
          >
            Submit for Execution
          </Button>
        )}
        {isSubmitted && (
          <Chip label="Submitted" color="success" />
        )}
      </Box>

      {/* Override Dialog */}
      <Dialog open={overrideDialogOpen} onClose={() => setOverrideDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Override {commitType === 'supply' ? 'Supply' : 'Allocation'} Commit</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" paragraph>
            Override reason will be captured for performance tracking and agent learning (RLHF).
          </Typography>
          <TextField
            select
            fullWidth
            label="Override Reason"
            value={overrideReason}
            onChange={(e) => setOverrideReason(e.target.value)}
            margin="normal"
          >
            {OVERRIDE_REASONS.map((r) => (
              <MenuItem key={r.value} value={r.value}>{r.label}</MenuItem>
            ))}
          </TextField>
          <TextField
            fullWidth
            multiline
            rows={3}
            label="Additional Notes"
            value={overrideNotes}
            onChange={(e) => setOverrideNotes(e.target.value)}
            margin="normal"
            placeholder="Describe what you changed and why..."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOverrideDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            color="warning"
            onClick={handleOverrideConfirm}
            disabled={!overrideReason}
          >
            Confirm Override
          </Button>
        </DialogActions>
      </Dialog>

      {/* Reject Dialog */}
      <Dialog open={rejectDialogOpen} onClose={() => setRejectDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Reject {commitType === 'supply' ? 'Supply' : 'Allocation'} Commit</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" paragraph>
            The agent will re-generate with adjusted constraints.
          </Typography>
          <TextField
            fullWidth
            multiline
            rows={3}
            label="Rejection Reason"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            margin="normal"
            placeholder="Explain why this commit should be rejected..."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRejectDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            color="error"
            onClick={handleRejectConfirm}
            disabled={!rejectReason}
          >
            Confirm Reject
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
};

export default CommitReviewPanel;
