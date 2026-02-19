/**
 * Artifact Lineage Visualization
 *
 * Shows the hash-chain lineage for any cascade artifact:
 * PE → SupBP → SC → SBP → AC
 *
 * Traces upstream (where did this come from?) and downstream (what depends on this?).
 */
import React, { useState, useEffect } from 'react';
import {
  Box, Paper, Typography, Chip, CircularProgress,
  Stepper, Step, StepLabel, StepContent, IconButton, Tooltip,
} from '@mui/material';
import {
  ArrowForward as ArrowIcon,
  Settings as SOPIcon,
  Assignment as MRSIcon,
  LocalShipping as SupplyIcon,
  Category as AllocationIcon,
  PlayArrow as ExecutionIcon,
  OpenInNew as OpenIcon,
} from '@mui/icons-material';
import { getArtifactLineage } from '../../services/planningCascadeApi';

const TYPE_CONFIG = {
  policy_envelope: { label: 'Policy Envelope', icon: <SOPIcon fontSize="small" />, color: '#1976d2' },
  supply_baseline_pack: { label: 'Supply Baseline Pack', icon: <MRSIcon fontSize="small" />, color: '#388e3c' },
  supply_commit: { label: 'Supply Commit', icon: <SupplyIcon fontSize="small" />, color: '#f57c00' },
  solver_baseline_pack: { label: 'Solver Baseline Pack', icon: <AllocationIcon fontSize="small" />, color: '#7b1fa2' },
  allocation_commit: { label: 'Allocation Commit', icon: <AllocationIcon fontSize="small" />, color: '#c62828' },
};

const ArtifactChip = ({ type, hash, status, isCurrent, onClick }) => {
  const config = TYPE_CONFIG[type] || { label: type, color: '#666' };
  return (
    <Chip
      icon={config.icon}
      label={`${config.label} #${hash}`}
      size="small"
      variant={isCurrent ? 'filled' : 'outlined'}
      sx={{
        borderColor: config.color,
        bgcolor: isCurrent ? config.color : 'transparent',
        color: isCurrent ? '#fff' : config.color,
        cursor: onClick ? 'pointer' : 'default',
      }}
      onClick={onClick}
      deleteIcon={status ? undefined : undefined}
    />
  );
};

const ArtifactLineage = ({ artifactType, artifactId, onNavigate }) => {
  const [lineage, setLineage] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (artifactType && artifactId) {
      loadLineage();
    }
  }, [artifactType, artifactId]);

  const loadLineage = async () => {
    try {
      setLoading(true);
      const data = await getArtifactLineage(artifactType, artifactId);
      setLineage(data);
    } catch (error) {
      console.error('Failed to load lineage', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <CircularProgress size={20} />;
  }

  if (!lineage) {
    return <Typography variant="body2" color="text.secondary">No lineage data available</Typography>;
  }

  const allNodes = [
    ...lineage.upstream.map(n => ({ ...n, section: 'upstream' })),
    { ...lineage.artifact, section: 'current' },
    ...lineage.downstream.map(n => ({ ...n, section: 'downstream' })),
  ];

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography variant="subtitle2" gutterBottom>
        Artifact Lineage (Hash Chain)
      </Typography>
      <Box display="flex" alignItems="center" flexWrap="wrap" gap={1}>
        {allNodes.map((node, i) => (
          <React.Fragment key={`${node.type}-${node.id}`}>
            {i > 0 && <ArrowIcon fontSize="small" color="action" />}
            <Box>
              <ArtifactChip
                type={node.type}
                hash={node.hash}
                status={node.status}
                isCurrent={node.section === 'current'}
                onClick={onNavigate ? () => onNavigate(node.type, node.id) : undefined}
              />
              {node.status && (
                <Chip
                  label={node.status}
                  size="small"
                  variant="outlined"
                  sx={{ ml: 0.5, height: 20, fontSize: '0.65rem' }}
                  color={
                    node.status === 'submitted' ? 'success' :
                    node.status === 'overridden' ? 'warning' :
                    node.status === 'rejected' ? 'error' : 'default'
                  }
                />
              )}
            </Box>
          </React.Fragment>
        ))}
      </Box>
      {lineage.artifact?.source && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          Source: {lineage.artifact.source === 'autonomy_sim' ? 'Autonomy Simulation' : 'Customer Input'}
        </Typography>
      )}
    </Paper>
  );
};

export default ArtifactLineage;
