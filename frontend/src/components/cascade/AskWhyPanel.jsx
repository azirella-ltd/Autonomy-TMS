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
  Shield as AuthorityIcon,
  Speed as GuardrailIcon,
  BarChart as AttributionIcon,
  CompareArrows as CounterfactualIcon,
} from '@mui/icons-material';
import {
  askWhySupplyCommit, askWhyAllocationCommit,
  askWhyTRMDecision, askWhyGNNNode,
} from '../../services/planningCascadeApi';

/**
 * commitType: 'supply' | 'allocation' | 'trm' | 'gnn'
 * commitId: decision ID for supply/allocation/trm, or unused for gnn
 * configId, nodeId, modelType: required for gnn mode
 * level: 'VERBOSE' | 'NORMAL' | 'SUCCINCT' for trm/gnn modes
 */
const AskWhyPanel = ({
  commitId,
  commitType = 'supply',
  configId,
  nodeId,
  modelType = 'sop',
  level = 'NORMAL',
}) => {
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
      let data;
      switch (commitType) {
        case 'trm':
          data = await askWhyTRMDecision(commitId, level);
          break;
        case 'gnn':
          data = await askWhyGNNNode(configId, nodeId, modelType, level);
          break;
        case 'allocation':
          data = await askWhyAllocationCommit(commitId);
          break;
        default:
          data = await askWhySupplyCommit(commitId);
      }
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

            {/* === Context-Aware Sections (from AgentContextExplainer) === */}
            {/* Use agent_context from supply/allocation, or top-level for trm/gnn */}
            <AgentContextSections context={reasoning.agent_context || (commitType === 'trm' || commitType === 'gnn' ? reasoning : null)} />
          </Paper>
        )}
      </Collapse>
    </Box>
  );
};

/**
 * Sub-component rendering authority, guardrails, attribution, and counterfactual sections
 * from a ContextAwareExplanation dict.
 */
const AgentContextSections = ({ context }) => {
  const [showAuthority, setShowAuthority] = useState(false);
  const [showGuardrails, setShowGuardrails] = useState(false);
  const [showAttribution, setShowAttribution] = useState(false);
  const [showCounterfactuals, setShowCounterfactuals] = useState(false);

  if (!context) return null;

  const { authority, guardrails, attribution, counterfactuals, prediction_interval, explanation } = context;

  const guardrailColor = (status) => {
    if (status === 'WITHIN') return 'success';
    if (status === 'APPROACHING') return 'warning';
    return 'error';
  };

  return (
    <>
      {/* Context Explanation Text */}
      {explanation && (
        <>
          <Divider sx={{ my: 1 }} />
          <Typography variant="body2" sx={{ whiteSpace: 'pre-line', mb: 1 }}>
            {explanation}
          </Typography>
        </>
      )}

      {/* Authority Context */}
      {authority && (
        <>
          <Divider sx={{ my: 1 }} />
          <Box>
            <Box
              display="flex" alignItems="center" gap={0.5} mb={1}
              sx={{ cursor: 'pointer' }}
              onClick={() => setShowAuthority(!showAuthority)}
            >
              <AuthorityIcon fontSize="small" color="primary" />
              <Typography variant="subtitle2">Authority Context</Typography>
              <Chip
                label={authority.decision_classification}
                size="small"
                color={
                  authority.decision_classification === 'UNILATERAL' ? 'success'
                    : authority.decision_classification === 'ADVISORY' ? 'info'
                      : 'warning'
                }
              />
              <Chip label={authority.authority_level} size="small" variant="outlined" />
              {showAuthority ? <CollapseIcon fontSize="small" /> : <ExpandIcon fontSize="small" />}
            </Box>
            <Collapse in={showAuthority}>
              <Typography variant="body2" sx={{ pl: 1, mb: 1 }}>
                {authority.authority_statement}
              </Typography>
              {authority.approval_required && (
                <Alert severity="info" variant="outlined" sx={{ mb: 1 }}>
                  Requires {authority.approval_required} approval: {authority.approval_reason}
                </Alert>
              )}
            </Collapse>
          </Box>
        </>
      )}

      {/* Active Guardrails */}
      {guardrails?.length > 0 && (
        <>
          <Divider sx={{ my: 1 }} />
          <Box>
            <Box
              display="flex" alignItems="center" gap={0.5} mb={1}
              sx={{ cursor: 'pointer' }}
              onClick={() => setShowGuardrails(!showGuardrails)}
            >
              <GuardrailIcon fontSize="small" color="secondary" />
              <Typography variant="subtitle2">Active Guardrails</Typography>
              <Chip
                label={`${guardrails.filter(g => g.status !== 'WITHIN').length} alert(s)`}
                size="small"
                color={guardrails.some(g => g.status === 'EXCEEDED') ? 'error' : 'success'}
              />
              {showGuardrails ? <CollapseIcon fontSize="small" /> : <ExpandIcon fontSize="small" />}
            </Box>
            <Collapse in={showGuardrails}>
              <List dense disablePadding>
                {guardrails.map((g, i) => (
                  <ListItem key={i} disableGutters>
                    <ListItemIcon sx={{ minWidth: 24 }}>
                      <Box
                        sx={{
                          width: 10, height: 10, borderRadius: '50%',
                          bgcolor: guardrailColor(g.status) + '.main',
                        }}
                      />
                    </ListItemIcon>
                    <ListItemText
                      primary={g.name}
                      secondary={`Threshold: ${g.threshold} | Actual: ${typeof g.actual === 'number' ? g.actual.toFixed(2) : g.actual} | ${g.status}`}
                    />
                  </ListItem>
                ))}
              </List>
            </Collapse>
          </Box>
        </>
      )}

      {/* Feature Attribution */}
      {attribution?.features && Object.keys(attribution.features).length > 0 && (
        <>
          <Divider sx={{ my: 1 }} />
          <Box>
            <Box
              display="flex" alignItems="center" gap={0.5} mb={1}
              sx={{ cursor: 'pointer' }}
              onClick={() => setShowAttribution(!showAttribution)}
            >
              <AttributionIcon fontSize="small" color="info" />
              <Typography variant="subtitle2">Feature Attribution ({attribution.method})</Typography>
              {showAttribution ? <CollapseIcon fontSize="small" /> : <ExpandIcon fontSize="small" />}
            </Box>
            <Collapse in={showAttribution}>
              {/* Horizontal bars for top features */}
              {Object.entries(attribution.features)
                .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a))
                .slice(0, 5)
                .map(([name, importance]) => (
                  <Box key={name} display="flex" alignItems="center" gap={1} mb={0.5} pl={1}>
                    <Typography variant="caption" sx={{ minWidth: 120 }}>{name}</Typography>
                    <Box sx={{ flex: 1, bgcolor: 'grey.200', borderRadius: 1, height: 12, position: 'relative' }}>
                      <Box
                        sx={{
                          width: `${Math.abs(importance) * 100}%`,
                          bgcolor: importance >= 0 ? 'primary.main' : 'error.main',
                          borderRadius: 1,
                          height: '100%',
                        }}
                      />
                    </Box>
                    <Typography variant="caption" sx={{ minWidth: 40, textAlign: 'right' }}>
                      {(importance * 100).toFixed(0)}%
                    </Typography>
                  </Box>
                ))
              }
              {/* Neighbor attention for GNN */}
              {attribution.neighbor_attention && Object.keys(attribution.neighbor_attention).length > 0 && (
                <Box mt={1} pl={1}>
                  <Typography variant="caption" color="textSecondary">Neighbor Attention:</Typography>
                  <Box display="flex" gap={0.5} flexWrap="wrap" mt={0.5}>
                    {Object.entries(attribution.neighbor_attention)
                      .sort(([, a], [, b]) => b - a)
                      .slice(0, 5)
                      .map(([name, weight]) => (
                        <Chip key={name} label={`${name}: ${(weight * 100).toFixed(0)}%`} size="small" variant="outlined" />
                      ))
                    }
                  </Box>
                </Box>
              )}
            </Collapse>
          </Box>
        </>
      )}

      {/* Conformal Prediction Interval */}
      {prediction_interval && (
        <>
          <Divider sx={{ my: 1 }} />
          <Box pl={1}>
            <Typography variant="caption" color="textSecondary">
              Prediction Interval: [{prediction_interval.lower?.toFixed(1)} — {prediction_interval.upper?.toFixed(1)}]
              {prediction_interval.coverage && ` at ${(prediction_interval.coverage * 100).toFixed(0)}% coverage`}
              {prediction_interval.calibration_quality && ` (${prediction_interval.calibration_quality})`}
            </Typography>
          </Box>
        </>
      )}

      {/* Counterfactuals */}
      {counterfactuals?.length > 0 && (
        <>
          <Divider sx={{ my: 1 }} />
          <Box>
            <Box
              display="flex" alignItems="center" gap={0.5} mb={1}
              sx={{ cursor: 'pointer' }}
              onClick={() => setShowCounterfactuals(!showCounterfactuals)}
            >
              <CounterfactualIcon fontSize="small" />
              <Typography variant="subtitle2">What Would Change</Typography>
              {showCounterfactuals ? <CollapseIcon fontSize="small" /> : <ExpandIcon fontSize="small" />}
            </Box>
            <Collapse in={showCounterfactuals}>
              <List dense disablePadding>
                {counterfactuals.map((cf, i) => (
                  <ListItem key={i} disableGutters>
                    <ListItemText
                      primary={cf}
                      primaryTypographyProps={{ variant: 'body2', fontStyle: 'italic' }}
                    />
                  </ListItem>
                ))}
              </List>
            </Collapse>
          </Box>
        </>
      )}
    </>
  );
};

export default AskWhyPanel;
