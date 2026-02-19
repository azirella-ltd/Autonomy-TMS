/**
 * Ask Why Panel
 *
 * Shows detailed agent reasoning with evidence citations.
 * Used for both Supply Commits and Allocation Commits.
 */
import React, { useState } from 'react';
import {
  Box, Paper, Typography, Button, Collapse, Chip, Divider, Alert,
  List, ListItem, ListItemText, ListItemIcon,
} from '@mui/material';
import {
  QuestionAnswer as WhyIcon,
  ExpandMore as ExpandIcon,
  ExpandLess as CollapseIcon,
  Settings as PolicyIcon,
  Assignment as MethodIcon,
  TrendingUp as OutcomeIcon,
  Warning as RiskIcon,
  AccountTree as PeggingIcon,
} from '@mui/icons-material';
import { askWhySupplyCommit, askWhyAllocationCommit } from '../../services/planningCascadeApi';

const AskWhyPanel = ({ commitId, commitType = 'supply' }) => {
  const [expanded, setExpanded] = useState(false);
  const [reasoning, setReasoning] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleAskWhy = async () => {
    if (reasoning) {
      setExpanded(!expanded);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = commitType === 'supply'
        ? await askWhySupplyCommit(commitId)
        : await askWhyAllocationCommit(commitId);
      setReasoning(data);
      setExpanded(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load reasoning');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box>
      <Button
        variant="outlined"
        size="small"
        startIcon={<WhyIcon />}
        endIcon={expanded ? <CollapseIcon /> : <ExpandIcon />}
        onClick={handleAskWhy}
        disabled={loading}
        sx={{ mb: 1 }}
      >
        {loading ? 'Loading...' : expanded ? 'Hide Reasoning' : 'Ask Why'}
      </Button>

      {error && (
        <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>
      )}

      <Collapse in={expanded}>
        {reasoning && (
          <Paper variant="outlined" sx={{ p: 2, bgcolor: 'grey.50' }}>
            {/* Confidence */}
            <Box display="flex" alignItems="center" gap={1} mb={2}>
              <Typography variant="subtitle2">Agent Confidence:</Typography>
              <Chip
                label={`${((reasoning.agent_confidence || 0) * 100).toFixed(0)}%`}
                size="small"
                color={reasoning.agent_confidence > 0.8 ? 'success' : reasoning.agent_confidence > 0.5 ? 'warning' : 'error'}
              />
            </Box>

            {/* Main Reasoning */}
            {reasoning.agent_reasoning && (
              <Box mb={2}>
                <Typography variant="subtitle2" gutterBottom>Decision Reasoning</Typography>
                <Typography variant="body2">{reasoning.agent_reasoning}</Typography>
              </Box>
            )}

            <Divider sx={{ my: 1 }} />

            {/* Policy Envelope Context */}
            {reasoning.policy_envelope && (
              <Box mb={2}>
                <Box display="flex" alignItems="center" gap={0.5} mb={1}>
                  <PolicyIcon fontSize="small" color="primary" />
                  <Typography variant="subtitle2">Policy Envelope (θ)</Typography>
                  <Chip label={`#${reasoning.policy_envelope.hash}`} size="small" variant="outlined" />
                  <Chip
                    label={reasoning.policy_envelope.source === 'autonomy_sim' ? 'AI Generated' : 'Customer Input'}
                    size="small"
                    color={reasoning.policy_envelope.source === 'autonomy_sim' ? 'primary' : 'default'}
                  />
                </Box>
                <List dense disablePadding>
                  {reasoning.policy_envelope.otif_floors && (
                    <ListItem disableGutters>
                      <ListItemText
                        primary="OTIF Floors"
                        secondary={Object.entries(reasoning.policy_envelope.otif_floors)
                          .map(([k, v]) => `${k}: ${(v * 100).toFixed(0)}%`).join(', ')}
                      />
                    </ListItem>
                  )}
                  {reasoning.policy_envelope.safety_stock_targets && (
                    <ListItem disableGutters>
                      <ListItemText
                        primary="Safety Stock Targets (WOS)"
                        secondary={Object.entries(reasoning.policy_envelope.safety_stock_targets)
                          .map(([k, v]) => `${k}: ${v}`).join(', ')}
                      />
                    </ListItem>
                  )}
                </List>
              </Box>
            )}

            {/* SupBP / SBP Context */}
            {reasoning.supply_baseline_pack && (
              <Box mb={2}>
                <Box display="flex" alignItems="center" gap={0.5} mb={1}>
                  <MethodIcon fontSize="small" color="success" />
                  <Typography variant="subtitle2">Supply Baseline Pack</Typography>
                  <Chip label={`#${reasoning.supply_baseline_pack.hash}`} size="small" variant="outlined" />
                </Box>
                <Typography variant="body2">
                  {reasoning.supply_baseline_pack.candidates_count} candidate method{reasoning.supply_baseline_pack.candidates_count !== 1 ? 's' : ''} evaluated:
                  {' '}{reasoning.supply_baseline_pack.candidate_methods?.join(', ')}
                </Typography>
                {reasoning.selected_method && (
                  <Chip label={`Selected: ${reasoning.selected_method}`} size="small" color="success" sx={{ mt: 0.5 }} />
                )}
              </Box>
            )}

            {reasoning.solver_baseline_pack && (
              <Box mb={2}>
                <Box display="flex" alignItems="center" gap={0.5} mb={1}>
                  <MethodIcon fontSize="small" color="secondary" />
                  <Typography variant="subtitle2">Solver Baseline Pack</Typography>
                  <Chip label={`#${reasoning.solver_baseline_pack.hash}`} size="small" variant="outlined" />
                </Box>
                <Typography variant="body2">
                  {reasoning.solver_baseline_pack.candidates_count} allocation method{reasoning.solver_baseline_pack.candidates_count !== 1 ? 's' : ''} evaluated:
                  {' '}{reasoning.solver_baseline_pack.candidate_methods?.join(', ')}
                </Typography>
              </Box>
            )}

            {/* Projected Outcomes */}
            {reasoning.projected_outcomes && (
              <Box mb={2}>
                <Box display="flex" alignItems="center" gap={0.5} mb={1}>
                  <OutcomeIcon fontSize="small" color="info" />
                  <Typography variant="subtitle2">Projected Outcomes</Typography>
                </Box>
                <Box display="flex" gap={1}>
                  {reasoning.projected_outcomes.otif != null && (
                    <Chip label={`OTIF: ${(reasoning.projected_outcomes.otif * 100).toFixed(1)}%`} size="small" variant="outlined" />
                  )}
                  {reasoning.projected_outcomes.inventory_cost != null && (
                    <Chip label={`Cost: $${reasoning.projected_outcomes.inventory_cost.toLocaleString()}`} size="small" variant="outlined" />
                  )}
                  {reasoning.projected_outcomes.dos != null && (
                    <Chip label={`DOS: ${reasoning.projected_outcomes.dos.toFixed(1)}`} size="small" variant="outlined" />
                  )}
                </Box>
              </Box>
            )}

            {/* Risk Summary */}
            {(reasoning.integrity_violations?.length > 0 || reasoning.risk_flags?.length > 0) && (
              <Box>
                <Box display="flex" alignItems="center" gap={0.5} mb={1}>
                  <RiskIcon fontSize="small" color="warning" />
                  <Typography variant="subtitle2">Flags & Violations</Typography>
                </Box>
                {reasoning.integrity_violations?.length > 0 && (
                  <Alert severity="error" variant="outlined" sx={{ mb: 1 }}>
                    {reasoning.integrity_violations.length} integrity violation(s)
                  </Alert>
                )}
                {reasoning.risk_flags?.length > 0 && (
                  <Alert severity="warning" variant="outlined">
                    {reasoning.risk_flags.length} risk flag(s)
                  </Alert>
                )}
              </Box>
            )}
          </Paper>
        )}
      </Collapse>
    </Box>
  );
};

export default AskWhyPanel;
