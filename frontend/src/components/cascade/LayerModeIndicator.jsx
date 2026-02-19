/**
 * Layer Mode Indicator
 *
 * Shows the current mode of a cascade layer:
 * - ACTIVE (green) — layer purchased and AI-driven
 * - INPUT (blue) — customer provides manual input
 * - DISABLED (gray) — layer not available
 */
import React from 'react';
import { Chip, Tooltip, Box, Typography } from '@mui/material';
import {
  CheckCircle as ActiveIcon,
  Edit as InputIcon,
  Block as DisabledIcon,
} from '@mui/icons-material';

const MODE_CONFIG = {
  active: {
    label: 'ACTIVE',
    color: 'success',
    icon: <ActiveIcon fontSize="small" />,
    tooltip: 'This layer is AI-driven. Review and override agent outputs before they flow downstream.',
  },
  input: {
    label: 'INPUT',
    color: 'info',
    icon: <InputIcon fontSize="small" />,
    tooltip: 'Manual input required. Enter parameters that the upstream AI layer would have generated.',
  },
  disabled: {
    label: 'NOT PURCHASED',
    color: 'default',
    icon: <DisabledIcon fontSize="small" />,
    tooltip: 'This layer is not available in your current package. Contact sales to upgrade.',
  },
};

const LAYER_NAMES = {
  sop: 'S&OP Strategic Planning',
  mrs: 'MRS / Supply Baseline Pack',
  supply_agent: 'Supply Agent',
  allocation_agent: 'Allocation Agent',
  execution: 'Execution',
};

const LayerModeIndicator = ({ layer, mode, showLabel = true, size = 'medium' }) => {
  const config = MODE_CONFIG[mode] || MODE_CONFIG.disabled;
  const layerName = LAYER_NAMES[layer] || layer;

  return (
    <Tooltip title={config.tooltip}>
      <Box display="inline-flex" alignItems="center" gap={1}>
        <Chip
          icon={config.icon}
          label={config.label}
          color={config.color}
          size={size === 'small' ? 'small' : 'medium'}
          variant={mode === 'disabled' ? 'outlined' : 'filled'}
        />
        {showLabel && (
          <Typography variant="caption" color="text.secondary">
            {layerName}
          </Typography>
        )}
      </Box>
    </Tooltip>
  );
};

export default LayerModeIndicator;
